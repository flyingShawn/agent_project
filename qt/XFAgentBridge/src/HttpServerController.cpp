#include "HttpServerController.h"

#include <QHostAddress>
#include <QHttpServer>
#include <QHttpServerRequest>
#include <QJsonDocument>

#include <utility>

HttpServerController::HttpServerController(TaskReceiver *receiver, QObject *parent)
    : QObject(parent)
    , m_receiver(receiver)
{
    if (m_receiver) {
        connect(m_receiver, &TaskReceiver::logMessage, this, &HttpServerController::logMessage);
    }
}

HttpServerController::~HttpServerController()
{
    stop();
}

bool HttpServerController::start(quint16 port, const QStringList &allowedOrigins)
{
    stop();

    m_allowedOrigins = allowedOrigins;
    m_server = std::make_unique<QHttpServer>();
    configureRoutes();//配置 API 路由

    const quint16 actualPort = m_server->listen(QHostAddress::LocalHost, port);
    if (actualPort == 0) {
        m_server.reset();
        emit logMessage(QString("启动失败：127.0.0.1:%1 无法监听").arg(port));
        emit runningChanged(false, 0);
        return false;
    }

    m_port = actualPort;
    emit logMessage(QString("已监听 http://127.0.0.1:%1").arg(m_port));
    emit runningChanged(true, m_port);
    return true;
}

void HttpServerController::stop()
{
    if (!m_server) {
        return;
    }

    m_server.reset();
    m_port = 0;
    emit logMessage("本机 HTTP 接收服务已停止");
    emit runningChanged(false, 0);
}

bool HttpServerController::isRunning() const
{
    return m_server != nullptr && m_port != 0;
}

quint16 HttpServerController::port() const
{
    return m_port;
}

void HttpServerController::configureRoutes()
{
    // ──────────────────────────────────────────────────
    // 全局 CORS 处理（所有响应都自动加 CORS 头）
    // ──────────────────────────────────────────────────
    m_server->afterRequest([this](QHttpServerResponse &&response, const QHttpServerRequest &request) {
        return withCors(std::move(response), request);
    });

    m_server->route("/api/v1/health", QHttpServerRequest::Method::Get, [this](const QHttpServerRequest &request) {
        const QString origin = requestOrigin(request);
        if (!isAllowedOrigin(origin)) {
            return jsonResponse({{"success", false}, {"message", "Origin 不在允许列表"}}, QHttpServerResponse::StatusCode::Forbidden);
        }

        QJsonObject body;
        body.insert("success", true);
        body.insert("name", "XFAgentBridge");
        body.insert("status", "ok");
        body.insert("port", static_cast<int>(m_port));
        return jsonResponse(body, QHttpServerResponse::StatusCode::Ok);
    });

    // ──────────────────────────────────────────────────
    // 健康检查的 OPTIONS 预检请求
    // ──────────────────────────────────────────────────
    m_server->route("/api/v1/health", QHttpServerRequest::Method::Options, [this](const QHttpServerRequest &request) {
        return corsPreflightResponse(request);
    });

    // ──────────────────────────────────────────────────
    // 任务执行接口的 OPTIONS 预检请求
    // ──────────────────────────────────────────────────
    m_server->route("/api/v1/tasks/execute", QHttpServerRequest::Method::Options, [this](const QHttpServerRequest &request) {
        return corsPreflightResponse(request);
    });

    m_server->route("/api/v1/tasks/execute", QHttpServerRequest::Method::Post, [this](const QHttpServerRequest &request) {
        const QString origin = requestOrigin(request);
        if (!isAllowedOrigin(origin)) {
            return jsonResponse({{"success", false}, {"message", "Origin 不在允许列表"}}, QHttpServerResponse::StatusCode::Forbidden);
        }

        const QJsonDocument document = QJsonDocument::fromJson(request.body());
        if (!document.isObject()) {
            return jsonResponse({{"success", false}, {"message", "请求体必须是 JSON 对象"}}, QHttpServerResponse::StatusCode::BadRequest);
        }

        const TaskReceiveResult result = m_receiver->receive(document.object(), request.remoteAddress().toString());
        return jsonResponse(result.body, static_cast<QHttpServerResponse::StatusCode>(result.statusCode));
    });
}

bool HttpServerController::isAllowedOrigin(const QString &origin) const
{
    if (origin.isEmpty()) {
        return true;
    }
    for (const QString &allowed : m_allowedOrigins) {
        if (origin.compare(allowed.trimmed(), Qt::CaseInsensitive) == 0) {
            return true;
        }
    }
    return false;
}

QString HttpServerController::requestOrigin(const QHttpServerRequest &request) const
{
    return QString::fromUtf8(request.value("Origin")).trimmed();
}

QHttpServerResponse HttpServerController::withCors(QHttpServerResponse &&response, const QHttpServerRequest &request) const
{
    const QString origin = requestOrigin(request);
    if (isAllowedOrigin(origin) && !origin.isEmpty()) {
        response.setHeader("Access-Control-Allow-Origin", origin.toUtf8());
        response.setHeader("Vary", "Origin");
    }
    response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    response.setHeader("Access-Control-Allow-Headers", "Content-Type, X-External-User, X-External-Ts, X-External-Sign");
    response.setHeader("Access-Control-Allow-Private-Network", "true");
    response.setHeader("Access-Control-Max-Age", "600");
    return std::move(response);
}

QHttpServerResponse HttpServerController::jsonResponse(const QJsonObject &body, QHttpServerResponse::StatusCode status) const
{
    const QByteArray data = QJsonDocument(body).toJson(QJsonDocument::Compact);
    return QHttpServerResponse(QByteArrayLiteral("application/json"), data, status);
}

QHttpServerResponse HttpServerController::corsPreflightResponse(const QHttpServerRequest &request) const
{
    const QString origin = requestOrigin(request);
    if (!isAllowedOrigin(origin)) {
        return jsonResponse({{"success", false}, {"message", "Origin 不在允许列表"}}, QHttpServerResponse::StatusCode::Forbidden);
    }

    QHttpServerResponse response(QHttpServerResponse::StatusCode::NoContent);
    if (!origin.isEmpty()) {
        response.setHeader("Access-Control-Allow-Origin", origin.toUtf8());
        response.setHeader("Vary", "Origin");
    }
    response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    response.setHeader("Access-Control-Allow-Headers", "Content-Type, X-External-User, X-External-Ts, X-External-Sign");
    response.setHeader("Access-Control-Allow-Private-Network", "true");
    response.setHeader("Access-Control-Max-Age", "600");
    return response;
}
