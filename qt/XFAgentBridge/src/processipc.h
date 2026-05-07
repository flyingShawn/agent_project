#ifndef PROCESSIPC_H
#define PROCESSIPC_H

#include <QByteArray>
#include <QHash>
#include <QObject>
#include <QString>
#include <string>

class QLocalServer;
class QLocalSocket;

class ProcessIpc : public QObject
{
    Q_OBJECT
public:
    explicit ProcessIpc(QObject *parent = nullptr);
    ~ProcessIpc();

    // 两个进程只要传入同一个进程路径，就会得到同一个本地 IPC 名称。
    static QString serverNameFromProcessPath(const QString &processPath);
    // 主动连接对方的 QLocalServer，发送一帧 command + payload 后断开。
    static bool sendToProcess(const QString &processPath, int command, const QByteArray &payload, int timeoutMs = 300);
    static bool sendTextToProcess(const QString &processPath, int command, const QString &text, int timeoutMs = 300);

    // 当前进程调用 listenForProcess 后，就成为这个名称上的接收方。
    bool listenForProcess(const QString &processPath);
    bool listen(const QString &serverName);
    void close();

signals:
    void messageReceived(int command, QByteArray payload);

private slots:
    void onNewConnection();
    void onReadyRead();
    void onDisconnected();

private:
    static QByteArray buildFrame(int command, const QByteArray &payload);
    void parseSocketBuffer(QLocalSocket *socket);

private:
    QLocalServer *m_server;
    QString m_serverName;
    QHash<QLocalSocket*, QByteArray> m_buffers;
};

void msgToOtherProcess(std::string process, int nMsgCmd, std::string strMsg);

#endif // PROCESSIPC_H
