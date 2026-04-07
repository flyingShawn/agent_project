"""
测试 RAG 文档导入功能
"""
from pathlib import Path
from dotenv import load_dotenv
from agent_backend.rag_engine.settings import RagIngestSettings
from agent_backend.rag_engine.docling_parser import parse_document
from agent_backend.rag_engine.ingest import ingest_directory
from agent_backend.rag_engine.state import IngestStateStore

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

def test_parse_single_doc():
    """测试解析单个文档"""
    settings = RagIngestSettings()
    docs_dir = Path(settings.docs_dir)
    
    print("=" * 60)
    print("测试文档解析功能")
    print("=" * 60)
    
    if not docs_dir.exists():
        print(f"❌ 文档目录不存在: {docs_dir}")
        return
    
    files = list(docs_dir.glob("*"))
    if not files:
        print("❌ 文档目录为空")
        return
    
    print(f"✅ 找到 {len(files)} 个文件")
    print()
    
    for file in files[:3]:  # 只测试前3个文件
        print(f"正在测试: {file.name}")
        try:
            parsed = parse_document(file)
            print(f"  ✅ 解析成功")
            print(f"  - 内容类型: {parsed.content_type}")
            print(f"  - Markdown长度: {len(parsed.markdown)} 字符")
            if parsed.markdown:
                preview = parsed.markdown[:200].replace("\n", " ")
                print(f"  - 内容预览: {preview}...")
        except Exception as e:
            print(f"  ❌ 解析失败: {type(e).__name__}: {e}")
        print()


def test_full_ingest():
    """测试完整的文档导入流程"""
    print("=" * 60)
    print("测试完整文档导入流程")
    print("=" * 60)
    
    try:
        settings = RagIngestSettings()
        state = IngestStateStore(settings.state_path)
        
        result = ingest_directory(
            docs_dir=settings.docs_dir,
            settings=settings,
            state_store=state,
            mode="full"
        )
        
        print(f"✅ 导入成功！")
        print(f"  - 扫描文件数: {result.files_scanned}")
        print(f"  - 跳过文件数: {result.files_skipped}")
        print(f"  - 导入块数: {result.chunks_upserted}")
        
    except Exception as e:
        print(f"❌ 导入失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_parse_single_doc()
    print("\n" + "=" * 60 + "\n")
    test_full_ingest()
