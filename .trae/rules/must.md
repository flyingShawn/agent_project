若要删除文件，放到任务最后阶段再执行命令。

若修改库或配置文件，请注意docker配置中是否进行了相对应的同步修改。

logger.info或logger.warn等内容前，先添加有个换行符\n，比如logger.warning(f"\n向量化失败: {e}，使用随机向量回退")
