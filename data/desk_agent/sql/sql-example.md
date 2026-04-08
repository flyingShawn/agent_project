sql-example

#### 查询机器的详细信息

````sql
SELECT
	a.ID,
	a.Name_C,
	a.IP_C,
	a.MAC_C,
	c.UserName,
	a.zccmt,
	b.Deppath,
	f.paravalue,
	a.VersionNum,
CASESELECT
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
	(
		a.GroupID IN (SELECT gl.ID FROM s_Group gl) 
		OR a.id IN (
			SELECT b.mtid 
			FROM g_roleequiplist b
			LEFT JOIN g_adminroleright c ON c.RoleID = b.RoleID
			LEFT JOIN AdminInfo d ON d.id = c.AdminID 
			WHERE d.LogNum = 'admin'
		)
	)
ORDER BY INET_ATON(IP_C)
		WHEN d.ID IS NOT NULL THEN
		'在线' ELSE '不在线' 
	END AS 'IsOnline',
	e.SetValue,
	g.systemruntime,
	a.VersionTime,
	g.systemstarttime,
	brand.paravalue AS 'Brand',
	model.paravalue AS 'Model',
CASE
		
		WHEN disk.sysDiskUse IS NOT NULL 
		AND disk.sysDiskTotal IS NOT NULL 
		AND disk.sysDiskUse != '' 
		AND disk.sysDiskTotal != '' THEN
			CONCAT( disk.sysDiskUse, '/', disk.sysDiskTotal ) ELSE '' 
		END AS 'disk' 
	FROM
		( s_Machine a LEFT OUTER JOIN s_Group b ON a.GroupID = b.ID )
		LEFT OUTER JOIN s_User c ON a.ClientID = c.ID
		LEFT OUTER JOIN onlineinfo d ON a.id = d.MtID
		LEFT OUTER JOIN A_TableExtend e ON a.ID = e.MtID 
		AND TableName = 's_machine' 
		AND SetName = 'ShowMtName'
		LEFT OUTER JOIN a_clientpara f ON a.ID = f.MtID 
		AND f.Paraname = 'p_windowsversion'
		LEFT OUTER JOIN a_clientpara brand ON a.ID = brand.MtID 
		AND brand.Paraname = 'SystemManufacturer'
		LEFT OUTER JOIN a_clientpara model ON a.ID = model.MtID 
		AND model.Paraname = 'SystemProductName'
		LEFT OUTER JOIN (
		SELECT
			mtid,
			sysDiskUse,
			sysDiskTotal 
		FROM
			equipPara e1 
		WHERE
			id = (
			SELECT
				max( id ) 
			FROM
				equipPara e2 
			WHERE
				e2.mtid = e1.mtid 
			AND ( sysDiskUse IS NOT NULL OR sysDiskTotal IS NOT NULL ))) disk ON a.ID = disk.mtid
		LEFT OUTER JOIN a_machineruntime g ON a.ID = g.MtID 
	WHERE
		(
			a.GroupID IN ( SELECT gl.ID FROM s_Group gl ) 
			OR a.id IN (
			SELECT
				b.mtid 
			FROM
				g_roleequiplist b
				LEFT JOIN g_adminroleright c ON c.RoleID = b.RoleID
				LEFT JOIN AdminInfo d ON d.id = c.AdminID 
			WHERE
				d.LogNum = 'admin' 
			)) 
	ORDER BY
	INET_ATON(
	IP_C)
````

#### 查询部门的信息

部门主表 s_group

```sql
SELECT
    GroupName AS "部门名称",
    groupPhone AS "电话",
    Comment AS "备注",
    deppath AS "所属部门"
FROM
    s_group
ORDER BY
    GroupType ASC,
    id ASC;
```

##### 查询部门下更详细的信息

```sql
SELECT
    g.GroupName AS "部门名称",
    g.groupPhone AS "电话",
    g.Comment AS "备注",
    g.deppath AS "所属部门",
    g.GroupType AS "部门类型",
    -- 统计该部门下的设备数量
    (SELECT COUNT(*) FROM s_machine m WHERE m.Groupid = g.ID) AS "设备数量",
    -- 统计该部门下的用户数量
    (SELECT COUNT(*) FROM s_user u WHERE u.Groupid = g.ID) AS "用户数量"
FROM s_group g
ORDER BY g.GroupType ASC, g.id ASC
```



#### 查询全部设备的硬件资产信息

```sql
SELECT
    a.MtID AS "设备id",
    b.Name_c AS "计算机名",
    d.DepPath AS "所属部门",
    b.ZCNum AS "资产编号",
    c.UserName AS "用户名",
    a6.ParaValue AS "工作组",
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
    a.manufacturedate AS "生产日期",
    a.biosinfo AS "BIOS信息",
    Board AS "主板",
    CUP AS "CPU",
    ViewCard AS "显卡",
    Memory AS "内存",
    DiskInfo AS "硬盘信息",
    a5.ParaValue AS "硬盘序列号",
    DiskSize AS "硬盘大小",
    CASE
        WHEN netcardnum IS NULL THEN 1
        ELSE netcardnum
    END AS "网卡数量",
    NetCardList AS "网卡列表",
    USBList AS "USB设备",
    PrintList AS "打印机",
    CASE
        WHEN printercount IS NULL THEN 0
        ELSE printercount
    END AS "打印机数量",
    COMPortList AS "串口设备",
    CDRom AS "光驱",
    Mouse AS "鼠标",
    KeyBoard AS "键盘",
    a7.ParaValue AS "屏幕分辨率",
    a10.ParaValue AS "物理位置",
    b.zccmt AS "资产信息",
    g.NAME AS "楼宇信息",
    f.floor_name AS "楼层信息",
    a.sysIstTime AS "系统安装时间",
    a11.ParaValue AS "系统序列号"
FROM
    A_ClientHardInfo2 a
    LEFT OUTER JOIN s_Machine b ON a.MtID = b.ID
    LEFT OUTER JOIN s_User c ON c.ID = b.ClientID
    LEFT OUTER JOIN s_Group d ON d.ID = b.Groupid
    LEFT OUTER JOIN a_clientpara a1 ON a1.mtid = a.mtid AND a1.ParaName = 'systemmanufacturer'
    LEFT OUTER JOIN a_clientpara a2 ON a2.mtid = a.mtid AND a2.ParaName = 'systemproductname'
    LEFT OUTER JOIN a_clientpara a3 ON a3.mtid = a.mtid AND a3.Paraname = 'p_windowsversion'
    LEFT OUTER JOIN a_clientpara a4 ON a4.mtid = a.mtid AND a4.Paraname = 'P_BIOS_Manufacturer'
    LEFT OUTER JOIN a_clientpara a5 ON a5.mtid = a.mtid AND a5.Paraname = 'P_DiskSerialNum'
    LEFT OUTER JOIN a_clientpara a6 ON a6.mtid = a.mtid AND a6.ParaName = 'workgroup'
    LEFT OUTER JOIN a_clientpara a7 ON a7.mtid = a.mtid AND a7.ParaName = 'p_screensize'
    LEFT OUTER JOIN a_clientpara a10 ON a10.mtid = a.mtid AND a10.Paraname = 'macposition'
    LEFT OUTER JOIN a_clientpara a11 ON a11.mtid = a.mtid AND a11.Paraname = 'P_WindowsSystemID'
    LEFT OUTER JOIN floor f ON f.floor_id = b.building_floor
    LEFT OUTER JOIN building g ON g.building_id = f.building_id
WHERE
    ( IsNew = 1 )
ORDER BY
    d.GroupType,
    d.GroupName,
    a.MtID ASC
```



