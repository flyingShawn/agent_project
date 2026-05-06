#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

class TaskProcessor : public QObject {
    Q_OBJECT

public:
    explicit TaskProcessor(QObject *parent = nullptr);

    QJsonObject acceptOnly(const QJsonObject &payload, const QString &executionId) const;
};
