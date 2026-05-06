#include "MainWindow.h"

#include <QApplication>
#include <QCoreApplication>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    QCoreApplication::setOrganizationName("XFAgent");
    QCoreApplication::setOrganizationDomain("xfagent.local");
    QCoreApplication::setApplicationName("XFAgentBridge");
    QCoreApplication::setApplicationVersion("0.1.0");

    MainWindow window;
    window.show();

    return app.exec();
}
