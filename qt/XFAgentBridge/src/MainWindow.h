#pragma once

#include "BridgeSettings.h"
#include "HttpServerController.h"
#include "TaskReceiver.h"

#include <QMainWindow>

class QLabel;
class QPlainTextEdit;
class QPushButton;
class QSpinBox;
class QSystemTrayIcon;
class QTextEdit;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

protected:
    void closeEvent(QCloseEvent *event) override;

private:
    void setupUi();
    void setupTray();
    void loadSettingsToUi();
    BridgeSettingsData collectSettingsFromUi() const;
    void startServer();
    void stopServer();
    void saveSettings();
    void updateRunningState(bool running, quint16 port);
    void appendLog(const QString &message);

    BridgeSettings m_settingsStore;
    BridgeSettingsData m_settings;
    TaskReceiver m_receiver;
    HttpServerController m_server;

    QLabel *m_statusLabel = nullptr;
    QLabel *m_endpointLabel = nullptr;
    QLabel *m_storageLabel = nullptr;
    QSpinBox *m_portSpin = nullptr;
    QPlainTextEdit *m_originsEdit = nullptr;
    QTextEdit *m_logEdit = nullptr;
    QPushButton *m_startButton = nullptr;
    QPushButton *m_stopButton = nullptr;
    QPushButton *m_saveButton = nullptr;
    QSystemTrayIcon *m_trayIcon = nullptr;
};
