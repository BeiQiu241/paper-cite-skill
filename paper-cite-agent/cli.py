"""CLI 入口：paper-cite-agent 命令行接口。"""

import sys
from pathlib import Path

import typer

# 确保模块路径
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

app = typer.Typer(
    name="paper-cite-agent",
    help="论文参考文献检索 Agent：自动分析论文内容，推荐并标注参考文献。",
    add_completion=False,
)


@app.command()
def main(
    docx_file: Path = typer.Argument(
        ...,
        help="论文 Word 文件路径",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    config: Path = typer.Option(
        None,
        "--config", "-c",
        help="配置文件路径（默认使用同目录 config.yaml）",
        exists=False,
    ),
    output_dir: Path = typer.Option(
        None,
        "--output", "-o",
        help="输出目录（默认与输入文件相同目录）",
    ),
    cn_count: int = typer.Option(
        5,
        "--cn",
        help="推荐中文文献数量（默认 5）",
        min=0,
        max=20,
    ),
    en_count: int = typer.Option(
        5,
        "--en",
        help="推荐英文文献数量（默认 5）",
        min=0,
        max=20,
    ),
    ref_format: str = typer.Option(
        "APA",
        "--format", "-f",
        help="参考文献格式：APA 或 IEEE",
    ),
):
    """
    分析论文 Word 文件，搜索匹配的学术文献，并在文档中标注引用位置。

    示例：
        paper-cite-agent thesis.docx
        paper-cite-agent thesis.docx --cn 4 --en 3 --format IEEE
        paper-cite-agent thesis.docx --output ./output
    """
    from main import run_pipeline, load_config
    import yaml

    typer.echo(f"\n📖 正在处理: {docx_file}")

    # 如果通过命令行指定了参数，临时覆盖配置
    cfg = load_config(str(config) if config else None)
    cfg.setdefault("ranking", {})["top_k"] = cn_count + en_count
    cfg.setdefault("output", {})["reference_format"] = ref_format.upper()

    # 将覆盖后的配置写入临时文件
    import tempfile, os

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        yaml.dump(cfg, tmp, allow_unicode=True)
        tmp_config = tmp.name

    try:
        result = run_pipeline(
            docx_path=str(docx_file),
            config_path=tmp_config,
            output_dir=str(output_dir) if output_dir else None,
            cn_count=cn_count,
            en_count=en_count,
        )
    except KeyboardInterrupt:
        typer.echo("\n⚠ 用户中断操作", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"\n❌ 运行失败: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)
    finally:
        os.unlink(tmp_config)


if __name__ == "__main__":
    app()
