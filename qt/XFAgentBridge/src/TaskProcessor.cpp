#include "TaskProcessor.h"

#include <QJsonArray>

TaskProcessor::TaskProcessor(QObject *parent)
    : QObject(parent)
{
}

QJsonObject TaskProcessor::acceptOnly(const QJsonObject &payload, const QString &executionId) const
{
    const QString requestId = payload.value("request_id").toString();
    const QString taskId = payload.value("task_id").toString();

    QJsonObject item;
    item.insert("name", taskId.isEmpty() ? "任务" : taskId);
    item.insert("status", "success");
    item.insert("message", "提交成功，正在处理");

    QJsonArray items;
    items.append(item);

    QJsonObject data;
    data.insert("local_execution_id", executionId);
    data.insert("request_id", requestId);
    data.insert("status", "accepted");
    data.insert("items", items);
    return data;
}
