# SQL查询样本库

本文件包含桌面管理系统的常见SQL查询样本，用于RAG检索增强SQL生成。

#### 查询指定IP的机器信息

适用场景：当用户询问某IP地址对应的设备详细信息时使用，包括设备名称、IP、MAC、用户名、所属部门、操作系统、在线状态等。

关键表：s\_machine, s\_group, s\_user, onlineinfo, a\_clientpara, a\_machineruntime

```sql
SELECT
    a.ID AS "设备id",
    a.Name_C AS "设备名称",
    a.IP_C AS "ip地址",
    a.MAC_C AS "mac地址",
    c.UserName AS "用户名",
    a.zccmt AS "资产信息",
    b.Deppath AS "所属部门",
    f.paravalue AS "操作系统",
    a.VersionNum AS "客户端版本",
    CASE WHEN d.ID IS NOT NULL THEN '在线' ELSE '不在线' END AS "是否在线",
    g.systemruntime AS "机器运行时间(小时)",
    a.VersionTime AS "客户端安装时间",
    g.systemstarttime AS "客户端开机时间",
    brand.paravalue AS "品牌",
    model.paravalue AS "型号"
FROM
    s_Machine a
    LEFT OUTER JOIN s_Group b ON a.GroupID = b.ID
    LEFT OUTER JOIN s_User c ON a.ClientID = c.ID
    LEFT OUTER JOIN onlineinfo d ON a.id = d.MtID
    LEFT OUTER JOIN a_clientpara f ON a.ID = f.MtID AND f.Paraname = 'p_windowsversion'
    LEFT OUTER JOIN a_clientpara brand ON a.ID = brand.MtID AND brand.Paraname = 'SystemManufacturer'
    LEFT OUTER JOIN a_clientpara model ON a.ID = model.MtID AND model.Paraname = 'SystemProductName'
    LEFT OUTER JOIN a_machineruntime g ON a.ID = g.MtID
WHERE
    a.IP_C = :ip
ORDER BY INET_ATON(a.IP_C)
```

***

#### 查询机器在线信息

适用场景：当用户查询在线设备列表，在线机器信息，客户端在线状态，需展示这个语句中的几列，在线机器一定开机了 ，0.0小时为刚开机不久。

关键表：s\_machine, s\_group, s\_user, onlineinfo, a\_clientpara, a\_machineruntime

```sql
SELECT
    a.ID AS "设备id",
    a.Name_C AS "设备名称",
    a.IP_C AS "ip地址",
    a.MAC_C AS "mac地址",
    c.UserName AS "用户名",
    a.zccmt AS "资产信息",
    b.Deppath AS "所属部门",
    f.paravalue AS "操作系统",
    a.VersionNum AS "客户端版本",
    g.systemruntime AS "机器运行时间(小时)",
    g.systemstarttime AS "客户端开机时间"
FROM
    s_Machine a
    LEFT OUTER JOIN s_Group b ON a.GroupID = b.ID
    LEFT OUTER JOIN s_User c ON a.ClientID = c.ID
    LEFT OUTER JOIN onlineinfo d ON a.id = d.MtID
    LEFT OUTER JOIN a_clientpara f ON a.ID = f.MtID AND f.Paraname = 'p_windowsversion'
    LEFT OUTER JOIN a_machineruntime g ON a.ID = g.MtID
WHERE
	d.ID IS NOT NULL
ORDER BY INET_ATON(a.IP_C)
```

***

#### 查询部门信息

适用场景：当用户询问部门列表、部门名称、部门层级结构等信息时使用。GroupType

关键表：s\_group

```sql
SELECT
    g.GroupName AS "部门名称",
    g.groupPhone AS "电话",
    g.Comment AS "备注",
    g.deppath AS "所属部门",
    g.GroupType AS "部门类型",
    (SELECT COUNT(*) FROM s_machine m WHERE m.Groupid = g.ID) AS "设备数量",
    (SELECT COUNT(*) FROM s_user u WHERE u.Groupid = g.ID) AS "用户数量"
FROM s_group g
ORDER BY g.GroupType ASC, g.id ASC
```

***

#### 查询全部设备的硬件资产信息

适用场景：当用户询问设备硬件资产、CPU、内存、硬盘、显卡、品牌型号等信息时使用。

关键表：A\_ClientHardInfo2, s\_Machine, s\_User, s\_Group, a\_clientpara

```sql
SELECT
    a.MtID AS "设备id",
    b.Name_c AS "计算机名",
    d.DepPath AS "所属部门",
    b.ZCNum AS "资产编号",
    c.UserName AS "用户名",
    b.IP_c AS "IP地址",
    b.Mac_C AS "MAC地址",
    a3.paravalue AS "操作系统",
    CASE
        WHEN b.systemactive = 1 THEN '已激活'
        WHEN b.systemactive = 2 THEN '未激活'
        ELSE ''
    END AS "系统激活",
    a1.ParaValue AS "品牌",
    a2.ParaValue AS "型号",
    a.serialnum AS "序列号",
    Board AS "主板",
    CUP AS "CPU",
    ViewCard AS "显卡",
    Memory AS "内存",
    DiskInfo AS "硬盘信息",
    DiskSize AS "硬盘大小",
    CASE WHEN netcardnum IS NULL THEN 1 ELSE netcardnum END AS "网卡数量",
    a7.ParaValue AS "屏幕分辨率"
FROM
    A_ClientHardInfo2 a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    LEFT OUTER JOIN s_Group d ON d.ID = b.Groupid
    LEFT OUTER JOIN a_clientpara a1 ON a1.mtid = a.mtid AND a1.ParaName = 'systemmanufacturer'
    LEFT OUTER JOIN a_clientpara a2 ON a2.mtid = a.mtid AND a2.ParaName = 'systemproductname'
    LEFT OUTER JOIN a_clientpara a3 ON a3.mtid = a.mtid AND a3.Paraname = 'p_windowsversion'
    LEFT OUTER JOIN a_clientpara a7 ON a7.mtid = a.mtid AND a7.ParaName = 'p_screensize'
WHERE
    (IsNew = 1)
ORDER BY
    d.GroupType,
    d.GroupName,
    a.MtID ASC
```

***


#### 查询最近设备远程记录

适用场景：当用户询问客户端远程记录时使用。managerid是发起远程的管理机id，其他内容是被远程的客户端设备信息。

关键表：a\_remoteinfo

```sql
SELECT
	ip AS "IP地址",
	machinename AS "设备机器名",
	department AS "所属部门",
	lasttime AS "最近远程时间",
	mtid AS "远程设备ID",
	managerid AS "管理机ID"
FROM
	a_remoteinfo
```

***

#### 查询指定的管理机信息

适用场景：需要查询指定管理机ID或指定管理机IP地址对应的具体信息时使用

关键表：manageinfo

```sql
SELECT
	id AS "记录ID",
	ManageIP AS "管理IP",
	MachineName AS "管理机机器名",
	versionnum AS "管理机版本"
FROM
	manageinfo
```

***

#### 查询最近管理员日志

适用场景：需要查询最近管理员相关操作日志是使用。管理员id去manageinfo表联查可获取管理机机器名

关键表：adminlog

```sql
SELECT
	adminid AS "管理员ID",
	doinfo AS "操作内容",
	adddate AS "操作时间",
	ip AS "操作IP",
	mac AS "MAC地址"
FROM
	adminlog
```

***

#### 查询设备开关机日志

适用场景：需要查询某一段时间内所有客户端（机器、设备、电脑）开关机时间信息

关键表：a\_OpenCloseLog, s\_Machine, s\_Group

```sql
SELECT
	a.LogonUser AS "登录用户",
	d.GroupName AS "部门名称",
	b.Name_C AS "设备名称",
	b.IP_C AS "IP地址",
	a.OpenTime AS "开机时间",
	a.CloseTime AS "关机时间"
FROM
	a_OpenCloseLog a
LEFT OUTER JOIN s_machine b ON a.MtID = b.ID
LEFT OUTER JOIN s_Group d ON b.Groupid = d.ID 
WHERE
	a.OpenTime >= '2026-4-10 00:00:00' 
	AND a.OpenTime <= '2026-4-10 23:59:59' 
ORDER BY
	a.OpenTime DESC
```

#### 查询设备usb使用日志

适用场景：需要查询某一段时间内所有客户端（机器、设备、电脑）usb使用和操作日志，查询有接入U盘的电脑相关

关键表：USBDB, s\_Machine, s\_Group

```sql
SELECT
	a.LogonUser AS "登录用户",
	d.GroupName AS "部门名称",
	b.Name_C AS "设备名称",
	b.IP_C AS "IP地址",
	a.USBPlugTime AS "使用时间",
	CASE a.IsForbit 
		WHEN 1 THEN '插入' 
		ELSE '拔出' 
	END AS "USB操作",
	a.DeviceDesc AS "usb名称",
	a.FriendName AS "usb备注",
	CASE a.isinsert 
		WHEN 1 THEN '禁用' 
		ELSE '未禁用' 
	END AS "USB禁用状态"
FROM
	USBDB a
LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
LEFT OUTER JOIN s_Group d ON b.Groupid = d.ID 
WHERE
	a.USBPlugTime >= '2026-4-10 00:00:00' 
	AND a.USBPlugTime <= '2026-4-10 23:59:59' 
ORDER BY
	a.USBPlugTime DESC
```

#### 客户端在线数量

```sql
SELECT
	COUNT(*) AS "在线客户端数量" 
FROM
	onlineinfo;
```

#### 客户端总数

```sql
SELECT
	COUNT(*) AS "设备数量" 
FROM
	s_machine;
```

#### 部门总数

```sql
SELECT
	COUNT(*) AS "部门数量" 
FROM
	s_group;
```

#### USB日志记录数数量

```sql
SELECT
	COUNT(*) AS "日志数" 
FROM
	usbdb;
```

#### 客户端空闲数量

```
```



#### 老旧资产设备查询

----

#### 终端空闲情况
在线设备数量，分布的部门
