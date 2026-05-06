#pragma once

#include <QString>
#include <QStringList>

struct BridgeSettingsData {
    quint16 port = 17891;
    QStringList allowedOrigins;
};

class BridgeSettings {
public:
    static constexpr quint16 DefaultPort = 17891;

    BridgeSettingsData load() const;
    void save(const BridgeSettingsData &data) const;

    QString storagePath() const;
    QString taskLogPath() const;

private:
    QString appDataDir() const;
    QStringList defaultAllowedOrigins() const;
};
