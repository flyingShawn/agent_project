#include "TaskReceiver.h"

#include <QDateTime>
#include <QFile>
#include <QJsonDocument>
#include <QUuid>

TaskReceiver::TaskReceiver(const BridgeSettings *settings, QObject *parent)
    : QObject(parent)
    , m_settings(settings)
    , m_processor(this)
{
}

TaskReceiveResult TaskReceiver::receive(const QJsonObject &payload, const QString &remoteAddress)
{
    const QString validationError = validate(payload);
    if (!validationError.isEmpty()) {
        return {
            400,
            {
                {"success", false},
                {"message", validationError},
                {"result_type", "text"},
            },
        };
    }

    const QString executionId = QUuid::createUuid().toString(QUuid::WithoutBraces);
    const QJsonObject data = m_processor.acceptOnly(payload, executionId);

    QJsonObject body;
    body.insert("success", true);
    body.insert("message", "任务已接收");
    body.insert("result_type", "status_list");
    body.insert("data", data);

    QJsonObject record;
    record.insert("received_at", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    record.insert("remote_address", remoteAddress);
    record.insert("local_execution_id", executionId);
    record.insert("task_id", payload.value("task_id").toString());
    record.insert("agent_type", payload.value("agent_type").toString());
    record.insert("request", payload);
    record.insert("response", body);

    if (!appendRecord(record)) {
        emit logMessage("任务已接收，但写入本地日志失败");
    }

//    const QString jsonStr = QJsonDocument(payload).toJson(QJsonDocument::Indented);
//    emit logMessage(QString("收到任务 [%1]:\n%2").arg(payload.value("task_id").toString(), jsonStr));

    const QString jsonRecord = QJsonDocument(record).toJson(QJsonDocument::Indented);
    emit logMessage(QString("组合record [%1]:\n%2").arg(payload.value("task_id").toString(), jsonRecord));

    emit taskAccepted(payload.value("task_id").toString(), executionId, payload);
    return {200, body};
}

QString TaskReceiver::validate(const QJsonObject &payload) const
{
    if (payload.value("agent_type").toString().trimmed().isEmpty()) {
        return "agent_type 不能为空";
    }
    if (payload.value("task_id").toString().trimmed().isEmpty()) {
        return "task_id 不能为空";
    }
    if (!payload.value("params").isObject()) {
        return "params 必须是对象";
    }
    return {};
}

bool TaskReceiver::appendRecord(const QJsonObject &record) const
{
    if (!m_settings) {
        return false;
    }

    QFile file(m_settings->taskLogPath());
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        return false;
    }

    file.write(QJsonDocument(record).toJson(QJsonDocument::Compact));
    file.write("\n");
    return true;
}
