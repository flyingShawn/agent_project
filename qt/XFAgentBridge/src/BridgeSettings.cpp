#include "BridgeSettings.h"

#include <QDir>
#include <QSettings>
#include <QStandardPaths>

BridgeSettingsData BridgeSettings::load() const
{
    QSettings settings;

    BridgeSettingsData data;
    data.port = settings.value("server/port", DefaultPort).toUInt();
    data.allowedOrigins = settings.value("server/allowedOrigins", defaultAllowedOrigins()).toStringList();

    if (data.port == 0) {
        data.port = DefaultPort;
    }
    if (data.allowedOrigins.isEmpty()) {
        data.allowedOrigins = defaultAllowedOrigins();
    }
    return data;
}

void BridgeSettings::save(const BridgeSettingsData &data) const
{
    QSettings settings;
    settings.setValue("server/port", data.port);
    settings.setValue("server/allowedOrigins", data.allowedOrigins);
}

QString BridgeSettings::storagePath() const
{
    return appDataDir();
}

QString BridgeSettings::taskLogPath() const
{
    return QDir(appDataDir()).filePath("received_tasks.jsonl");
}

QString BridgeSettings::appDataDir() const
{
    QString path = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if (path.isEmpty()) {
        path = QDir::home().filePath(".xfaagentbridge");
    }
    QDir().mkpath(path);
    return path;
}

QStringList BridgeSettings::defaultAllowedOrigins() const
{
    return {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://ytsoft.asuscomm.com:3000",
        "http://ytsoft.asuscomm.com",
        "https://ytsoft.asuscomm.com",
    };
}
