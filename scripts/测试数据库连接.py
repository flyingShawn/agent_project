"""
数据库连接测试脚本

用途：
    - 测试数据库连接是否正常
    - 验证数据库配置是否正确
    - 检查表是否可以访问

使用方法：
    python scripts/测试数据库连接.py
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def load_env():
    """加载.env文件"""
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        print("❌ 错误：未找到 .env 文件")
        print("请先创建 .env 文件（可以从 .env.example 复制）")
        return False
    
    print("✅ 找到 .env 文件")
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
    
    return True

def test_database_connection():
    """测试数据库连接"""
    print("\n" + "="*60)
    print("  数据库连接测试")
    print("="*60 + "\n")
    
    database_url = os.getenv("DATABASE_URL", "")
    db_host = os.getenv("DB_HOST", "")
    db_name = os.getenv("DB_NAME", "")
    
    if not database_url and not db_host:
        print("❌ 数据库未配置")
        print("\n请在 .env 文件中配置数据库连接：")
        print("  方式一（推荐）：")
        print("    DB_TYPE=mysql")
        print("    DB_HOST=localhost")
        print("    DB_PORT=3306")
        print("    DB_NAME=your_database")
        print("    DB_USER=root")
        print("    DB_PASSWORD=your_password")
        print("  方式二：")
        print("    DATABASE_URL=mysql+pymysql://user:password@host:port/database")
        return False
    
    print(f"✅ 数据库已配置")
    
    if database_url:
        if database_url.startswith("mysql"):
            db_type = "MySQL"
        elif database_url.startswith("postgresql"):
            db_type = "PostgreSQL"
        else:
            db_type = "未知"
        print(f"   数据库类型：{db_type}")
    else:
        db_type = os.getenv("DB_TYPE", "mysql")
        print(f"   数据库类型：{db_type}")
        print(f"   主机地址：{db_host}")
        print(f"   数据库名：{db_name}")
    
    try:
        from sqlalchemy import create_engine, text
        print("✅ SQLAlchemy 已安装")
    except ImportError:
        print("❌ SQLAlchemy 未安装")
        print("   请运行：pip install sqlalchemy pymysql")
        return False
    
    print("\n正在测试数据库连接...")
    
    try:
        from agent_backend.core.config_helper import get_database_url
        db_url = get_database_url()
        
        if not db_url:
            print("❌ 无法生成数据库连接URL")
            return False
        
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print("✅ 数据库连接成功！")
            
            if db_type == "mysql" or db_type == "MySQL":
                result = conn.execute(text("SELECT VERSION()"))
                version = result.fetchone()[0]
                print(f"   MySQL版本：{version}")
            elif db_type == "postgresql" or db_type == "PostgreSQL":
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                print(f"   PostgreSQL版本：{version.split(',')[0]}")
            
            print("\n正在检查表访问权限...")
            
            result = conn.execute(text("SHOW TABLES" if db_type in ["mysql", "MySQL"] else 
                                      "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"✅ 可以访问数据库表（共 {len(tables)} 个表）")
                print(f"   前5个表：{', '.join(tables[:5])}")
            else:
                print("⚠️  数据库中没有表")
            
            return True
            
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        print("\n常见问题：")
        print("  1. 检查数据库服务是否启动")
        print("  2. 检查用户名和密码是否正确")
        print("  3. 检查数据库名称是否正确")
        print("  4. 检查网络连接和防火墙设置")
        return False

def main():
    """主函数"""
    print("\n" + "="*60)
    print("  桌管智能体 - 数据库连接测试工具")
    print("="*60)
    
    if not load_env():
        sys.exit(1)
    
    success = test_database_connection()
    
    print("\n" + "="*60)
    if success:
        print("✅ 数据库配置正确，可以使用Text-to-SQL功能！")
        print("\n下一步：")
        print("  1. 启动后端服务：python -m uvicorn agent_backend.main:app --reload")
        print("  2. 访问API文档：http://localhost:8000/docs")
        print("  3. 测试SQL查询：输入自然语言问题，如'查询有多少台设备'")
    else:
        print("❌ 数据库配置有问题，请检查配置后重试")
        print("\n请参考：help/数据库配置指南.md")
    print("="*60 + "\n")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
