SQL查询样本库

本文件包含桌面管理系统的常见SQL查询样本，用于RAG检索增强SQL生成。

#### 查询云桌面系统模板操作日志

适用场景：管理端「云桌面系统日志」中查询模板制作、安装、升级、VDI 等操作记录；可按时间、部门、模板类型筛选。`cmt` 为管理员相关说明或标识。

关键表：b_yunsystemlog, s_machine, s_group

```sql
SELECT
    a.id AS "记录ID",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.cmt AS "管理员备注",
    c.groupname AS "部门名称",
    a.content AS "事件内容",
    CASE a.templatetype
        WHEN 0 THEN '安装模板'
        WHEN 1 THEN '制作模板'
        WHEN 2 THEN '升级模板'
        WHEN 3 THEN '更新模板'
        WHEN 4 THEN '还原模式'
        WHEN 5 THEN '删除模板'
        WHEN 6 THEN '复制模板'
        WHEN 7 THEN '修改模板'
        WHEN 8 THEN 'VDI开机选项'
    END AS "操作类型",
    a.addtime AS "操作时间"
FROM
    b_yunsystemlog a
    LEFT JOIN s_machine b ON a.mtid = b.id
    LEFT JOIN s_group c ON c.id = b.groupid
ORDER BY
    a.addtime DESC
```

---

#### 查询上网/浏览器访问日志（单库）

适用场景：审计中「上网记录」类查询。若启用按日分库（`peerlan5_yyyyMMdd`），程序会将多日 `a_netdb` 做 `union all`，此处为未分库时的通用形态。

关键表：a_netdb, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    b.mac_c AS "MAC地址",
    a.logonuser AS "登录用户",
    c.username AS "用户名",
    d.groupname AS "部门名称",
    a.szcaption AS "窗口标题",
    a.netaddr AS "访问地址",
    a.szproductname AS "产品名",
    a.szcompanyname AS "公司名",
    a.szexename AS "进程名",
    a.nettime AS "访问时间",
    CASE a.isforbit WHEN 1 THEN '禁止访问' ELSE '允许访问' END AS "是否合规"
FROM
    a_netdb a
    INNER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON c.id = b.clientid
    INNER JOIN s_group d ON b.groupid = d.id
WHERE
    a.nettime >= :begin_time
    AND a.nettime <= :end_time
ORDER BY
    a.nettime DESC
```

---

#### 查询客户端登录/锁屏日志

适用场景：审计「客户端登录日志」，包含登录时间与锁屏时间。

关键表：a_loginlog, s_machine, s_group, s_user

```sql
SELECT
    a.id AS "记录ID",
    a.username AS "登录账号",
    d.username AS "用户姓名",
    c.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.logintime AS "登录时间",
    a.locktime AS "锁屏时间"
FROM
    a_loginlog a
    LEFT OUTER JOIN s_machine b ON a.nflag = b.id
    LEFT OUTER JOIN s_group c ON c.id = b.groupid
    LEFT OUTER JOIN s_user d ON d.usernum = a.username
```

---

#### 查询 DLP 登录日志

适用场景：数据防泄漏（DLP）客户端登录审计。

关键表：ydlploginlog, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    c.username AS "用户名",
    d.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.logintime AS "登录时间"
FROM
    ydlploginlog a
    LEFT OUTER JOIN s_machine b ON a.equipid = b.id
    LEFT OUTER JOIN s_user c ON c.id = a.userid
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 查询合规检测日志

适用场景：客户端合规检查结果（是否合规及说明）。

关键表：b_clientheguiinfo, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    a.logonuser AS "登录用户",
    c.username AS "用户名",
    d.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.addtime AS "检测时间",
    CASE a.ishegui WHEN 0 THEN '不合规' WHEN 1 THEN '合规' END AS "是否合规",
    a.heguiinfo AS "合规说明"
FROM
    b_clientheguiinfo a
    LEFT OUTER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON c.id = b.clientid
    LEFT OUTER JOIN s_group d ON d.id = b.groupid
```

---

#### 查询非法外联审计日志

适用场景：非授权外联行为审计。

关键表：a_outlinklog, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    c.username AS "用户名",
    d.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    b.mac_c AS "MAC地址",
    a.auditdate AS "审计时间"
FROM
    a_outlinklog a
    LEFT OUTER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON b.clientid = c.id
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 查询打印日志

适用场景：终端打印审计（文档名、打印机、页数、份数等）。

关键表：printdb, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    a.logonuser AS "登录用户",
    c.username AS "用户名",
    d.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.docname AS "文档名",
    a.printername AS "打印机",
    a.pages AS "页数",
    a.copys AS "份数",
    a.printtime AS "打印时间"
FROM
    printdb a
    LEFT OUTER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON c.id = b.clientid
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 查询系统安全告警日志（全量部门，管理员视角）

适用场景：终端触发的系统安全类告警。非超级管理员时程序会按 `rolegroupmap_alert` 与管理员角色过滤部门，以下为不限定管理员的通用骨架。

关键表：alertsystemdb, s_machine, s_group

```sql
SELECT
    a.id AS "记录ID",
    d.groupname AS "部门名称",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.alertmsg AS "告警内容",
    a.alerttime AS "告警时间"
FROM
    alertsystemdb a
    INNER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 查询 WiFi 非白名单连接记录

适用场景：连接非白名单 WiFi 的记录。

关键表：wifinonwhitelistrecords, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    c.username AS "用户名",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.connecttime AS "连接时间",
    a.ssid AS "SSID",
    a.macaddress AS "MAC地址"
FROM
    wifinonwhitelistrecords a
    LEFT OUTER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON b.clientid = c.id
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 查询 UKEY 解锁日志

适用场景：UKEY 解锁、远程解锁、OA 登录等方式记录。

关键表：b_ukeyunlocklog, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    d.groupname AS "部门名称",
    a.logonuser AS "登录用户",
    c.username AS "用户名",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    a.logontime AS "解锁时间",
    CASE a.logontype
        WHEN 0 THEN 'UKEY解锁'
        WHEN 1 THEN '远程解锁'
        WHEN 2 THEN '超级管理员解锁'
        WHEN 3 THEN 'OA登录'
    END AS "解锁类型",
    a.ukeyid AS "UKeyID",
    a.yuid AS "YUID",
    a.oaid AS "OAID"
FROM
    b_ukeyunlocklog a
    LEFT OUTER JOIN s_machine b ON a.mtid = b.id
    LEFT OUTER JOIN s_user c ON c.id = b.clientid
    LEFT OUTER JOIN s_group d ON d.id = b.groupid
```

---

#### 查询远程开机操作日志

适用场景：远程开机任务对客户端执行记录。

关键表：c_mtbootclient, s_machine, s_user, s_group

```sql
SELECT
    a.id AS "记录ID",
    c.username AS "用户名",
    b.name_c AS "设备名称",
    b.ip_c AS "IP地址",
    b.mac_c AS "MAC地址",
    a.mtoptime AS "操作时间"
FROM
    c_mtbootclient a
    LEFT OUTER JOIN s_machine b ON a.mtbootid = b.id
    LEFT OUTER JOIN s_user c ON c.id = b.clientid
    LEFT OUTER JOIN s_group d ON b.groupid = d.id
```

---

#### 按部门统计终端数量

适用场景：首页或报表中按部门汇总已注册终端数量。

关键表：s_machine, s_group

```sql
SELECT
    b.groupname AS "部门名称",
    a.groupid AS "部门ID",
    COUNT(*) AS "终端数量"
FROM
    s_machine a
    INNER JOIN s_group b ON a.groupid = b.id
GROUP BY
    a.groupid,
    b.groupname
ORDER BY
    COUNT(*) DESC
```

---

#### 查询管理员账号列表（非单条）

适用场景：密码策略、管理员信息维护中列举已设置登录名的管理员（含密码修改时间）。

关键表：admininfo

```sql
SELECT
    lognum AS "登录名",
    username AS "显示名"
FROM
    admininfo
WHERE
    lognum IS NOT NULL
    AND lognum != ''
```

---

#### 按软件名称统计安装杀毒终端数

适用场景：首页或报表中查看各安装软件在多少台终端上安装。

关键表：a_sdinstallinfo, s_Machine

```sql
SELECT
    a.DisplayName AS "软件名称",
    COUNT(DISTINCT a.MtID) AS "安装终端数"
FROM
    a_sdinstallinfo a
    INNER JOIN s_Machine b ON a.MtID = b.ID
GROUP BY
    a.DisplayName
ORDER BY
    COUNT(DISTINCT a.MtID) DESC
```

---

#### 查询终端已安装杀毒软件明细

适用场景：按部门、机器查看客户端上报的已安装软件列表；杀毒软件名称在界面中可能对 `OfficeScan` 等做展示别名（如 TrustOne）。`IsInstall = 1` 表示已安装。

关键表：a_sdinstallinfo, s_Machine, s_User, s_Group

```sql
SELECT
    d.GroupName AS "部门名称",
    a.Name_C AS "计算机名",
    a.IP_C AS "IP地址",
    a.MAC_C AS "MAC地址",
    CASE
        WHEN c.UserName IS NULL THEN b.LogonUser
        ELSE c.UserName
    END AS "用户",
    CASE
        WHEN b.DisplayName LIKE '%OfficeScan%' THEN 'TrustOne'
        ELSE b.DisplayName
    END AS "软件显示名",
    b.DisplayName AS "原始名称",
    b.VersionNum AS "版本号",
    CASE b.IsInstall WHEN 1 THEN '是' ELSE '否' END AS "是否已安装"
FROM
    s_Machine a
    LEFT OUTER JOIN a_sdinstallinfo b ON a.ID = b.MtID
    LEFT OUTER JOIN s_User c ON c.ID = a.ClientID
    LEFT OUTER JOIN s_Group d ON a.GroupID = d.ID
WHERE
    b.IsInstall = 1
```

---

#### 查询程序运行/软件进程审计日志

适用场景：审计「程序日志」——进程路径、打开/关闭时间、产品名、厂商及是否策略禁止运行等。大数据量且按日分库时，表 `a_softdb` 可能位于 `peerlan5_yyyyMMdd` 库并由程序 `UNION ALL`。

关键表：a_softdb, s_Machine, s_User, s_Group

```sql
SELECT
    a.ID AS "记录ID",
    CASE a.IsForbit WHEN 1 THEN '禁止运行' ELSE '允许运行' END AS "策略结果",
    a.LogonUser AS "登录用户",
    c.UserName AS "用户名",
    d.GroupName AS "部门名称",
    b.Name_C AS "设备名称",
    b.IP_C AS "IP地址",
    a.ProcessPath AS "进程路径",
    a.OpenTime AS "开始时间",
    a.CloseTime AS "结束时间",
    a.ProductName AS "产品名",
    a.CompanyName AS "厂商"
FROM
    a_softdb a
    INNER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    INNER JOIN s_Group d ON b.Groupid = d.ID
WHERE
    a.OpenTime >= :begin_time
    AND a.OpenTime <= :end_time
ORDER BY
    a.OpenTime DESC
```

---

#### 查询开放端口报警

适用场景：检测到异常监听端口时的告警记录。

关键表：a_alert_port, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.port AS "端口",
    a.addtime AS "报警时间"
FROM
    a_alert_port a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    a.addtime DESC
```

---

#### 查询软件资产变化报警

适用场景：策略关注的软件被安装/卸载/变更时产生的告警。

关键表：a_alert_installsoft, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.AlertType AS "告警类型",
    a.SoftName AS "软件名称",
    a.AlertTime AS "告警时间"
FROM
    a_alert_installsoft a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    a.AlertTime DESC
```

---

#### 查询终端 IP 地址变化报警

适用场景：终端 IP 变更审计（过滤掉由 `0.0.0.0` 等无效旧值产生的记录时可按业务增加条件）。

关键表：a_alert_ipchange, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.szOldIP AS "变更前IP",
    a.szNewIP AS "变更后IP",
    a.ChangeTime AS "变更时间"
FROM
    a_alert_ipchange a
    LEFT OUTER JOIN s_Machine b ON a.nMtID = b.ID
WHERE
    a.szOldIP != '0.0.0.0'
ORDER BY
    a.ChangeTime DESC
```

---

#### 查询系统安全报警（首页数据源）

适用场景：客户端上报的系统安全类告警。部分界面与首页汇总均使用 `alertsystemdb`（以实际库表命名为准）。

关键表：alertsystemdb, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.AlertMsg AS "告警内容",
    a.AlertTime AS "告警时间"
FROM
    alertsystemdb a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    a.AlertTime DESC
```

---

#### 查询程序运行类报警（alertsoftdb）

适用场景：与策略不匹配的程序运行告警（与审计库 `a_softdb` 不同，此为报警汇总表）。

关键表：alertsoftdb, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.SoftName AS "软件/程序名",
    a.SoftTime AS "报警时间"
FROM
    alertsoftdb a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    a.SoftTime DESC
```

---

#### 查询违规上网报警（AlertNetDB）

适用场景：访问违规网址触发的告警。

关键表：alertnetdb, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    a.NetAddr AS "网址",
    a.NetTime AS "访问时间"
FROM
    alertnetdb a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    a.NetTime DESC
```

---

#### 查询文件外发类报警（fileoperatedb）

适用场景：浏览器/USB/IM/网盘等渠道外发文件的告警（`nType` 含义与客户端上报一致）。

关键表：fileoperatedb, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    CASE a.nType
        WHEN 4 THEN '浏览器外发'
        WHEN 5 THEN 'USB外发'
        WHEN 8 THEN 'QQ外发'
        WHEN 9 THEN '阿里旺旺外发'
        WHEN 11 THEN 'Skype外发'
        WHEN 14 THEN '微信外发'
        WHEN 16 THEN '百度网盘外发'
        WHEN 17 THEN '腾讯微云外发'
    END AS "外发类型",
    a.FileSize AS "文件大小",
    CASE a.IsBackFile WHEN 1 THEN '是' ELSE '否' END AS "是否备份",
    a.ProcessName AS "进程名",
    a.FileOpTime AS "操作时间"
FROM
    fileoperatedb a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
WHERE
    a.nType IN (4, 5, 8, 9, 10, 14, 16, 17)
ORDER BY
    a.FileOpTime DESC
```

---

####  *查询自动分配部门前的设备基础数据*

适用场景：`dllmanage/MachineAutoGroup.cpp` 中“立即生效自动分组”前读取全量设备用于匹配 IP 段/机器名规则并改部门。

关键表：s_Machine

```sql
SELECT
    IP_C AS "IP地址",
    Name_C AS "设备名称",
    ID AS "设备ID",
    mtcmt AS "设备备注",
    mtpingpai AS "设备品牌",
    GroupID AS "当前部门ID"
FROM
    s_Machine
```

---

#### 查询部门下用户列表（含可扩展注册字段）

适用场景：`dllmanage/DepUserDlg.cpp` 用户管理列表查询。用于按部门展示用户账号、工号、联系方式、身份信息和 para1~para6 扩展字段。

关键表：s_User, s_Group

```sql
SELECT
    a.ID AS "用户ID",
    a.UserName AS "用户名",
    a.UserNum AS "工号",
    b.GroupName AS "部门名称",
    a.WorkUnit AS "单位",
    a.UserPwd AS "密码",
    a.telnum AS "电话",
    a.usermail AS "邮箱",
    a.shenfeninfo AS "身份信息",
    a.szCmt AS "备注"
FROM
    s_User a
    INNER JOIN s_Group b ON a.GroupID = b.ID
```

---

#### 查询用户注册审核列表

适用场景：用户审核/补录列表，关联机器、注册表、用户表和部门，展示是否审核、审核时间、是否已注册等。

关键表：s_Machine, a_userRegister, s_User, s_Group

```sql
SELECT
    d.ID AS "注册记录ID",
    a.UserName AS "用户名",
    b.IP_C AS "IP地址",
    b.Mac_C AS "MAC地址",
    b.Name_C AS "设备名称",
    CASE
        WHEN d.hasaudit = 1 THEN '是'
        WHEN d.hasaudit = 0 THEN '否'
        ELSE ''
    END AS "是否审核",
    d.useraudittime AS "审核时间",
    c.GroupName AS "部门名称",
    a.usernum AS "工号",
    a.usermail AS "邮箱",
    a.telnum AS "电话",
    a.shenfeninfo AS "身份信息",
    a.WorkUnit AS "单位",
    a.szCmt AS "备注",
    b.ID AS "设备ID",
    d.nflag1,
    d.nflag2,
    CASE WHEN d.ID > 0 THEN '是' ELSE '否' END AS "是否注册"
FROM
    s_Machine b
    LEFT OUTER JOIN a_userRegister d ON d.mtid = b.ID
    LEFT OUTER JOIN s_User a ON d.userid = a.ID
    LEFT OUTER JOIN s_Group c ON c.ID = b.GroupID
ORDER BY
    d.addtime DESC
```

---

#### 按出厂日期筛查较老旧硬件资产（主板/整机生产信息偏旧）

适用场景：硬件资产条件查询中按「出厂日期」判断老旧设备；主板生产日期早于「当前日期往前推 N 年」的阈值。`:years` 为年限数字（如 `5` 表示机龄约 5 年及以上），默认为5。仅取当前有效硬件快照 `IsNew = 1`。

关键表：A_ClientHardInfo2, s_Machine, s_User, s_Group

MySQL：

```sql
SELECT
    a.MtID AS "设备ID",
    b.Name_C AS "计算机名",
    d.DepPath AS "所属部门",
    a.ManufactureDate AS "出厂日期",
    a.Board AS "主板",
    a.biosinfo AS "BIOS信息",
    b.IP_C AS "IP地址"
FROM
    A_ClientHardInfo2 a
    INNER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    LEFT OUTER JOIN s_Group d ON d.ID = b.GroupID
WHERE
    a.IsNew = 1
    AND a.ManufactureDate IS NOT NULL
    AND a.ManufactureDate <= DATE_SUB(CURDATE(), INTERVAL :years YEAR)
ORDER BY
    a.ManufactureDate ASC,
    a.MtID ASC
```

SQL Server：

```sql
SELECT
    a.MtID AS "设备ID",
    b.Name_C AS "计算机名",
    d.DepPath AS "所属部门",
    a.ManufactureDate AS "出厂日期",
    a.Board AS "主板",
    a.biosinfo AS "BIOS信息",
    b.IP_C AS "IP地址"
FROM
    A_ClientHardInfo2 a
    INNER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    LEFT OUTER JOIN s_Group d ON d.ID = b.GroupID
WHERE
    a.IsNew = 1
    AND a.ManufactureDate IS NOT NULL
    AND a.ManufactureDate <= DATEADD(YEAR, -:years, CAST(GETDATE() AS DATE))
ORDER BY
    a.ManufactureDate ASC,
    a.MtID ASC
```

---

#### 查询在线终端空闲状态（实时）

适用场景：左侧部门树刷新在线列表时读取客户端上报的空闲标志；与 `LeftTree.cpp::OnRefreshDep`、`MainWinTh.cpp` 中 `OnlineInfo` 查询一致。`nIsIdle` 非 0 一般表示客户端处于空闲（具体含义以产品版本为准）。

关键表：onlineinfo, s_Machine

```sql
SELECT
    a.MtID AS "设备ID",
    b.Name_C AS "设备名称",
    b.IP_C AS "IP地址",
    b.Mac_C AS "MAC地址",
    a.ID AS "在线记录ID",
    b.MtCmt AS "机器备注",
    b.GroupID AS "部门ID",
    a.nIsIdle AS "是否空闲"
FROM
    onlineinfo a
    INNER JOIN s_Machine b ON a.MtID = b.ID
ORDER BY
    b.Name_C ASC
```

---

#### 按安装软件名统计终端台数（a_installsoft，与「软件统计」页同源）

适用场景：`SoftCount.cpp`「安装软件名称 / 终端安装台数」统计：基于注册表同步的 `a_installsoft`，按软件名聚合。可选按部门名、软件名关键字筛选（与界面下拉、关键字一致）。

关键表：a_installsoft, s_Machine, s_Group

```sql
SELECT
    a.softname AS "安装软件名称",
    COUNT(a.softname) AS "终端安装台数"
FROM
    a_installsoft a
    INNER JOIN s_Machine b ON a.MtID = b.ID
    INNER JOIN s_Group c ON b.GroupID = c.ID
WHERE
    a.id > 0
GROUP BY
    a.softname
ORDER BY
    COUNT(a.softname) DESC
```

说明：与界面一致可按部门追加 `AND c.GroupName = '某部门'`，按名称追加 `AND a.softname LIKE '%关键字%'。

---

#### 查询指定终端已安装软件列表（a_installsoft）

适用场景：远程管理「卸载软件」等界面按机器读取已安装软件及卸载命令

关键表：a_installsoft

```sql
SELECT
    SoftName AS "软件名称",
    VersionNum AS "版本号",
    UninstallString AS "卸载命令"
FROM
    a_installsoft
ORDER BY
    SoftName ASC
```

---

#### 查询软件安装变更日志（c_soft_installinfo）

适用场景：审计报表中「软件安装日志」

关键表：c_soft_installinfo, s_Machine, s_User, s_Group

```sql
SELECT
    a.ID AS "记录ID",
    c.UserName AS "用户名",
    d.GroupName AS "部门名称",
    b.Name_C AS "设备名称",
    b.IP_C AS "IP地址",
    a.soft_name AS "软件名称",
    a.soft_version AS "软件版本",
    a.soft_installdate AS "安装时间",
    a.soft_method AS "安装方式"
FROM
    c_soft_installinfo a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    LEFT OUTER JOIN s_Group d ON b.GroupID = d.ID
ORDER BY
    a.soft_installdate DESC
```

---

