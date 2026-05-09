#### 任务推送文件分发：任务列表

适用场景：按时间段查询任务，查询任务推送记录

关键表：a_taskfilesendnew

```sql
SELECT
	id,
	taskname AS "任务名称",
	taskguid AS "任务GUID",
	filesize AS "文件大小",
	adddate AS "创建时间",
	totalnum AS "目标终端数",
	completenum AS "已完成数",
	CASE state
        WHEN 1 THEN '暂停'
        ELSE '执行'
	END AS "任务状态",
	failednum AS "分发失败数",
	execnum  AS "已执行数"
FROM
	a_taskfilesendnew 
WHERE
    AddDate >= :begin_time
    AND AddDate <= :end_time 
ORDER BY
	adddate DESC 
```

---

#### 任务推送文件分发：按任务查看各终端分发与执行情况

适用场景：给定 `TaskGUID`，查看每台终端是否分发成功、是否执行、结果说明

关键表：a_taskfilemtinfo, s_Machine

```sql
SELECT
    b.Name_C AS "设备名称",
    b.IP_C AS "IP地址",
    CASE e.IsSendOK
        WHEN 1 THEN '分发成功'
        WHEN 2 THEN '分发失败'
        ELSE '未分发'
    END AS "分发状态",
    CASE e.execstat
        WHEN 1 THEN '执行成功'
        WHEN 2 THEN '执行失败'
        ELSE '未执行'
    END AS "执行状态",
    e.result AS "结果说明",
    e.SendOkTime AS "分发完成时间",
    e.LastExecTime AS "最后执行时间"
FROM
    a_taskfilemtinfo e
    INNER JOIN s_machine b ON b.ID = e.MtID
WHERE
    e.TaskGUID = :task_guid
ORDER BY
    b.Name_C ASC
```
