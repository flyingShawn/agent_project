#include "processipc.h"

#include <QDataStream>
#include <QDebug>
#include <QIODevice>
#include <QLocalServer>
#include <QLocalSocket>
#include <cstdarg>
#include <cstdio>
#include <string>

namespace {
const quint32 kIpcMagic = 0x58434950; // XCIP
const quint16 kIpcVersion = 1;
const int kHeaderSize = sizeof(quint32) + sizeof(quint16) + sizeof(qint32) + sizeof(quint32);
const quint32 kMaxPayloadSize = 1024 * 1024;

// 固定字节序和 Qt 序列化版本，避免 Windows/Linux 或 Qt 版本差异影响协议。
void setStreamFormat(QDataStream &stream)
{
    stream.setByteOrder(QDataStream::BigEndian);
    stream.setVersion(QDataStream::Qt_4_8);
}

void ipcLog(const char *fmt, ...)
{
    char msg[1024];
    va_list args;
    va_start(args, fmt);
    vsnprintf(msg, sizeof(msg), fmt, args);
    va_end(args);
    qWarning("%s", msg);
}
}

ProcessIpc::ProcessIpc(QObject *parent)
    : QObject(parent),
      m_server(nullptr)
{
}

ProcessIpc::~ProcessIpc()
{
    close();
}

QString ProcessIpc::serverNameFromProcessPath(const QString &processPath)
{
    // QLocalServer 使用“名字”而不是文件路径连接；这里把历史上的进程路径转换成稳定名字，
    // 这样原来的 msgToOtherProcess("/zdgk/manage/views", ...) 调用习惯可以保留。
    QString text = processPath.trimmed();
    text.replace('\\', '/');
    while(text.endsWith('/'))
        text.chop(1);

    QString name;
    for(int i = 0; i < text.size(); ++i)
    {
        const QChar ch = text.at(i);
        if(ch.isLetterOrNumber())
            name.append(ch);
        else
            name.append('_');
    }

    name = name.trimmed();
    if(name.isEmpty())
        name = "unknown";
    return "zdgk_ipc_" + name;
}

bool ProcessIpc::sendToProcess(const QString &processPath, int command, const QByteArray &payload, int timeoutMs)
{
    const QString serverName = serverNameFromProcessPath(processPath);
    if(payload.size() > static_cast<int>(kMaxPayloadSize))
    {
        ipcLog("ProcessIpc::sendToProcess----payload-too-large cmd[%d] payload[%d]",
               command, payload.size());
        return false;
    }

    QLocalSocket socket;
    // 发送方流程：连接接收方 listen 的名字，连接不上说明对方进程未启动或未监听。
    socket.connectToServer(serverName);
    if(!socket.waitForConnected(timeoutMs))
    {
        QByteArray serverBytes = serverName.toUtf8();
        ipcLog("ProcessIpc::sendToProcess----connect-failed server[%s] error[%s]",
               serverBytes.constData(), socket.errorString().toUtf8().constData());
        return false;
    }

    // 本地 socket 是字节流，不能假设一次 readyRead 就是一条完整消息，所以发送前加固定帧头。
    const QByteArray frame = buildFrame(command, payload);
    qint64 written = socket.write(frame);
    if(written != frame.size() || (socket.bytesToWrite() > 0 && !socket.waitForBytesWritten(timeoutMs)))
    {
        QByteArray serverBytes = serverName.toUtf8();
        ipcLog("ProcessIpc::sendToProcess----write-failed server[%s] cmd[%d] error[%s]",
               serverBytes.constData(), command, socket.errorString().toUtf8().constData());
        socket.disconnectFromServer();
        return false;
    }

    socket.disconnectFromServer();
    if(socket.state() != QLocalSocket::UnconnectedState)
        socket.waitForDisconnected(timeoutMs);
    return true;
}

bool ProcessIpc::sendTextToProcess(const QString &processPath, int command, const QString &text, int timeoutMs)
{
    return sendToProcess(processPath, command, text.toUtf8(), timeoutMs);
}

bool ProcessIpc::listenForProcess(const QString &processPath)
{
    return listen(serverNameFromProcessPath(processPath));
}

/**
 * @brief ProcessIpc::listen 启动本地服务器监听指定的服务名
 * @param serverName 要监听的服务名称
 * @return bool 成功启动返回true，失败返回false
 */
bool ProcessIpc::listen(const QString &serverName)
{
    // 首先关闭可能已存在的连接
    close();

    // 创建本地服务器实例
    m_server = new QLocalServer(this);
    // 接收方流程：有新连接时取出 QLocalSocket，再监听它的 readyRead。
    connect(m_server, &QLocalServer::newConnection, this, &ProcessIpc::onNewConnection);

    // 设置服务器名称
    m_serverName = serverName;
    // 尝试监听指定名称的服务器
    if(!m_server->listen(m_serverName))
    {
        // Linux 上异常退出可能遗留 socket 文件，removeServer 后再 listen 一次。
        // Windows 命名管道通常不会残留，这里调用也安全。
        QLocalServer::removeServer(m_serverName);
        // 再次尝试监听
        if(!m_server->listen(m_serverName))
        {
            // 将服务器名称转为字节数组用于日志输出
            QByteArray serverBytes = m_serverName.toUtf8();
            // 记录监听失败的日志
            ipcLog("ProcessIpc::listen----failed server[%s] error[%s]",
                   serverBytes.constData(), m_server->errorString().toUtf8().constData());
            // 清理服务器资源
            delete m_server;
            m_server = nullptr;
            m_serverName.clear();
            return false;
        }
    }

    // 记录监听成功的日志
    QByteArray serverBytes = m_serverName.toUtf8();
    ipcLog("ProcessIpc::listen----success server[%s]", serverBytes.constData());
    return true;
}

void ProcessIpc::close()
{
    if(!m_server)
        return;

    // removeServer 只移除当前本地 IPC 名称，不会影响其他进程的其他监听名。
    m_server->close();
    QLocalServer::removeServer(m_serverName);
    m_buffers.clear();
    delete m_server;
    m_server = nullptr;
    m_serverName.clear();
}

/**
 * @brief 处理新的连接请求
 * 当有新的本地套接字连接请求到达时，此函数会被调用
 * 它会处理所有挂起的连接，并为每个新连接设置必要的信号槽连接
 */
void ProcessIpc::onNewConnection()
{
    // 循环处理所有挂起的连接，直到没有新的连接或服务器被关闭
    while(m_server && m_server->hasPendingConnections())
    {
        // 一个 QLocalServer 可以连续收到多个短连接，这里全部取出来接管。
        QLocalSocket *socket = m_server->nextPendingConnection();
        if(!socket)  // 检查socket是否有效，无效则跳过
            continue;

        connect(socket, &QLocalSocket::readyRead, this, &ProcessIpc::onReadyRead);
        connect(socket, &QLocalSocket::disconnected, this, &ProcessIpc::onDisconnected);
    }
}

void ProcessIpc::onReadyRead()
{
    QLocalSocket *socket = qobject_cast<QLocalSocket*>(sender());
    if(!socket)
        return;

    // readyRead 可能只到半包，也可能一次到多包；先累加到每个 socket 自己的缓存。
    m_buffers[socket].append(socket->readAll());
    parseSocketBuffer(socket);
}

void ProcessIpc::onDisconnected()
{
    QLocalSocket *socket = qobject_cast<QLocalSocket*>(sender());
    if(!socket)
        return;

    m_buffers.remove(socket);
    socket->deleteLater();
}

QByteArray ProcessIpc::buildFrame(int command, const QByteArray &payload)
{
    QByteArray frame;
    QDataStream out(&frame, QIODevice::WriteOnly);
    setStreamFormat(out);
    // 帧格式：magic + version + command + payloadSize + payload。
    out << kIpcMagic << kIpcVersion << static_cast<qint32>(command) << static_cast<quint32>(payload.size());
    if(!payload.isEmpty())
        out.writeRawData(payload.constData(), payload.size());
    return frame;
}

void ProcessIpc::parseSocketBuffer(QLocalSocket *socket)
{
    QByteArray &buffer = m_buffers[socket];
    while(buffer.size() >= kHeaderSize)
    {
        // 先读固定头。正文没收全时先返回，等下一次 readyRead 继续拼。
        QByteArray header = buffer.left(kHeaderSize);
        QDataStream in(&header, QIODevice::ReadOnly);
        setStreamFormat(in);

        quint32 magic = 0;
        quint16 version = 0;
        qint32 command = 0;
        quint32 payloadSize = 0;
        in >> magic >> version >> command >> payloadSize;

        if(magic != kIpcMagic || version != kIpcVersion || payloadSize > kMaxPayloadSize)
        {
            ipcLog("ProcessIpc::parseSocketBuffer----bad-frame magic[%u] version[%u] payload[%u]",
                   magic, version, payloadSize);
            socket->disconnectFromServer();
            return;
        }

        const int frameSize = kHeaderSize + static_cast<int>(payloadSize);
        if(buffer.size() < frameSize)
            return;

        // 拆出一条完整消息后从缓存移除，剩余数据可能正好是下一条消息。
        QByteArray payload = buffer.mid(kHeaderSize, payloadSize);
        buffer.remove(0, frameSize);
        emit messageReceived(command, payload);
    }
}

void msgToOtherProcess(std::string process, int nMsgCmd, std::string strMsg)
{
    // 兼容旧接口：旧代码仍按“目标进程路径 + 命令 + 字符串”调用，内部改用 QLocalSocket。
    ProcessIpc::sendTextToProcess(QString::fromStdString(process), nMsgCmd, QString::fromStdString(strMsg));
}
