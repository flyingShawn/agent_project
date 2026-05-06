#pragma once

#include "TaskReceiver.h"

#include <QHttpServerResponse>
#include <QObject>
#include <QStringList>
#include <memory>

class QHttpServer;
class QHttpServerRequest;

class HttpServerController : public QObject {
    Q_OBJECT

public:
    explicit HttpServerController(TaskReceiver *receiver, QObject *parent = nullptr);
    ~HttpServerController() override;

    bool start(quint16 port, const QStringList &allowedOrigins);
    void stop();

    bool isRunning() const;
    quint16 port() const;

signals:
    void runningChanged(bool running, quint16 port);
    void logMessage(const QString &message);

private:
    void configureRoutes();
    bool isAllowedOrigin(const QString &origin) const;
    QString requestOrigin(const QHttpServerRequest &request) const;
    QHttpServerResponse withCors(QHttpServerResponse &&response, const QHttpServerRequest &request) const;
    QHttpServerResponse jsonResponse(const QJsonObject &body, QHttpServerResponse::StatusCode status) const;
    QHttpServerResponse corsPreflightResponse(const QHttpServerRequest &request) const;

    TaskReceiver *m_receiver = nullptr;
    std::unique_ptr<QHttpServer> m_server;
    QStringList m_allowedOrigins;
    quint16 m_port = 0;
};
