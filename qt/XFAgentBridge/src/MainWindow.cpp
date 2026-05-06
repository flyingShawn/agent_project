#include "MainWindow.h"

#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QDateTime>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QMenu>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QJsonObject>
#include <QSpinBox>
#include <QStyle>
#include <QSystemTrayIcon>
#include <QTextEdit>
#include <QVBoxLayout>
#include <QWidget>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , m_settings(m_settingsStore.load())
    , m_receiver(&m_settingsStore, this)
    , m_server(&m_receiver, this)
{
    setupUi();
    setupTray();
    loadSettingsToUi();

    connect(&m_server, &HttpServerController::runningChanged, this, &MainWindow::updateRunningState);
    connect(&m_server, &HttpServerController::logMessage, this, &MainWindow::appendLog);
    connect(&m_receiver, &TaskReceiver::taskAccepted, this, [this](const QString &taskId, const QString &executionId, const QJsonObject &) {
        appendLog(QString("已接收任务：%1，local_execution_id=%2").arg(taskId, executionId));
    });

    startServer();
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (m_trayIcon && m_trayIcon->isVisible()) {
        hide();
        event->ignore();
        appendLog("窗口已隐藏到托盘，接收服务继续运行");
        return;
    }
    QMainWindow::closeEvent(event);
}

void MainWindow::setupUi()
{
    auto *central = new QWidget(this);
    auto *root = new QVBoxLayout(central);

    m_statusLabel = new QLabel(this);
    m_endpointLabel = new QLabel(this);
    m_storageLabel = new QLabel(this);

    auto *summaryLayout = new QFormLayout();
    summaryLayout->addRow("服务状态", m_statusLabel);
    summaryLayout->addRow("监听地址", m_endpointLabel);
    summaryLayout->addRow("数据目录", m_storageLabel);
    root->addLayout(summaryLayout);

    m_portSpin = new QSpinBox(this);
    m_portSpin->setRange(1024, 65535);

    m_originsEdit = new QPlainTextEdit(this);
    m_originsEdit->setPlaceholderText("每行一个允许的前端 Origin");
    m_originsEdit->setMaximumHeight(120);

    auto *configLayout = new QFormLayout();
    configLayout->addRow("端口", m_portSpin);
    configLayout->addRow("允许来源", m_originsEdit);
    root->addLayout(configLayout);

    auto *buttonLayout = new QHBoxLayout();
    m_startButton = new QPushButton("启动", this);
    m_stopButton = new QPushButton("停止", this);
    m_saveButton = new QPushButton("保存配置", this);
    buttonLayout->addWidget(m_startButton);
    buttonLayout->addWidget(m_stopButton);
    buttonLayout->addStretch();
    buttonLayout->addWidget(m_saveButton);
    root->addLayout(buttonLayout);

    m_logEdit = new QTextEdit(this);
    m_logEdit->setReadOnly(true);
    root->addWidget(m_logEdit, 1);

    setCentralWidget(central);
    setWindowTitle("XFAgentBridge");
    resize(720, 520);

    connect(m_startButton, &QPushButton::clicked, this, &MainWindow::startServer);
    connect(m_stopButton, &QPushButton::clicked, this, &MainWindow::stopServer);
    connect(m_saveButton, &QPushButton::clicked, this, &MainWindow::saveSettings);
}

void MainWindow::setupTray()
{
    if (!QSystemTrayIcon::isSystemTrayAvailable()) {
        appendLog("当前桌面环境不支持系统托盘，关闭窗口将退出程序");
        return;
    }

    m_trayIcon = new QSystemTrayIcon(style()->standardIcon(QStyle::SP_ComputerIcon), this);
    auto *menu = new QMenu(this);
    QAction *showAction = menu->addAction("显示窗口");
    QAction *quitAction = menu->addAction("退出");

    connect(showAction, &QAction::triggered, this, [this]() {
        showNormal();
        activateWindow();
    });
    connect(quitAction, &QAction::triggered, qApp, &QApplication::quit);
    connect(m_trayIcon, &QSystemTrayIcon::activated, this, [this](QSystemTrayIcon::ActivationReason reason) {
        if (reason == QSystemTrayIcon::DoubleClick || reason == QSystemTrayIcon::Trigger) {
            showNormal();
            activateWindow();
        }
    });

    m_trayIcon->setToolTip("XFAgentBridge");
    m_trayIcon->setContextMenu(menu);
    m_trayIcon->show();
}

void MainWindow::loadSettingsToUi()
{
    m_portSpin->setValue(m_settings.port);
    m_originsEdit->setPlainText(m_settings.allowedOrigins.join('\n'));
    m_storageLabel->setText(m_settingsStore.storagePath());
    updateRunningState(false, 0);
}

BridgeSettingsData MainWindow::collectSettingsFromUi() const
{
    BridgeSettingsData data;
    data.port = static_cast<quint16>(m_portSpin->value());

    const QStringList lines = m_originsEdit->toPlainText().split('\n');
    for (const QString &line : lines) {
        const QString origin = line.trimmed();
        if (!origin.isEmpty()) {
            data.allowedOrigins.append(origin);
        }
    }
    return data;
}

void MainWindow::startServer()
{
    m_settings = collectSettingsFromUi();
    m_settingsStore.save(m_settings);
    m_server.start(m_settings.port, m_settings.allowedOrigins);
}

void MainWindow::stopServer()
{
    m_server.stop();
}

void MainWindow::saveSettings()
{
    m_settings = collectSettingsFromUi();
    m_settingsStore.save(m_settings);
    appendLog("配置已保存，重启接收服务后生效");
}

void MainWindow::updateRunningState(bool running, quint16 port)
{
    m_statusLabel->setText(running ? "运行中" : "已停止");
    m_endpointLabel->setText(running ? QString("http://127.0.0.1:%1").arg(port) : "-");
    m_startButton->setEnabled(!running);
    m_stopButton->setEnabled(running);
}

void MainWindow::appendLog(const QString &message)
{
    if (!m_logEdit) {
        return;
    }
    const QString ts = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
    m_logEdit->append(QString("[%1] %2").arg(ts, message));
}
