#pragma once

#include "BridgeSettings.h"
#include "TaskProcessor.h"

#include <QJsonObject>
#include <QObject>
#include <QString>

struct TaskReceiveResult {
    int statusCode = 200;
    QJsonObject body;
};

class TaskReceiver : public QObject {
    Q_OBJECT

public:
    explicit TaskReceiver(const BridgeSettings *settings, QObject *parent = nullptr);

    TaskReceiveResult receive(const QJsonObject &payload, const QString &remoteAddress);

signals:
    void taskAccepted(const QString &taskId, const QString &executionId, const QJsonObject &payload);
    void logMessage(const QString &message);

private:
    QString validate(const QJsonObject &payload) const;
    bool appendRecord(const QJsonObject &record) const;

    const BridgeSettings *m_settings = nullptr;
    TaskProcessor m_processor;
};
