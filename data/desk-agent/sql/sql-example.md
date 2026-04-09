# SQL查询样本库

本文件包含桌面管理系统的常见SQL查询样本，用于RAG检索增强SQL生成。

---

#### 查询指定IP的机器详细信息

适用场景：当用户询问某IP地址对应的设备详细信息时使用，包括设备名称、IP、MAC、用户名、所属部门、操作系统、在线状态等。

关键表：s_machine, s_group, s_user, onlineinfo, a_clientpara, a_machineruntime

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

---

#### 查询部门信息

适用场景：当用户询问部门列表、部门名称、部门层级结构等信息时使用。

关键表：s_group

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

---

#### 查询全部设备的硬件资产信息

适用场景：当用户询问设备硬件资产、CPU、内存、硬盘、显卡、品牌型号等信息时使用。

关键表：A_ClientHardInfo2, s_Machine, s_User, s_Group, a_clientpara

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
