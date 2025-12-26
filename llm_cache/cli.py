"""Command-line interface for llm-cache."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

from .cache import Cache

console = Console()


@click.group()
@click.version_option()
def cli():
    """LLM Cache - Local caching layer for LLM API responses."""
    pass


@cli.command()
@click.option("--port", "-p", default=8080, help="Port to listen on")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default="openai")
@click.option("--target-url", help="Target API URL (overrides provider default)")
@click.option("--ttl", type=int, help="Default TTL in seconds")
@click.option("--cache-path", type=click.Path(), help="Path to cache database")
def serve(port, host, provider, target_url, ttl, cache_path):
    """Start the cache proxy server."""
    try:
        from .proxy import CacheProxy
    except ImportError:
        console.print("[red]Error: Flask and requests required.[/red]")
        console.print("Install with: pip install llm-cache[server]")
        raise SystemExit(1)

    cache_path = Path(cache_path) if cache_path else None
    cache = Cache(path=cache_path, ttl_seconds=ttl)

    proxy = CacheProxy(cache=cache, target_url=target_url, provider=provider)

    console.print(f"[green]Starting cache proxy on {host}:{port}[/green]")
    console.print(f"Provider: {provider}")
    console.print(f"Cache: {cache.path}")
    if ttl:
        console.print(f"TTL: {ttl}s")
    console.print()
    console.print("Configure your client to use:")
    console.print(f"  OPENAI_BASE_URL=http://{host}:{port}/v1")
    console.print()

    proxy.run(host=host, port=port)


@cli.command()
@click.option("--cache-path", type=click.Path(), help="Path to cache database")
def stats(cache_path):
    """Show cache statistics."""
    cache_path = Path(cache_path) if cache_path else None
    cache = Cache(path=cache_path)

    s = cache.stats()

    table = Table(title="Cache Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Cache Path", s["path"])
    table.add_row("Entries", str(s["entries"]))
    table.add_row("Size", f"{s['size_mb']} MB")
    table.add_row("Hits", str(s["hits"]))
    table.add_row("Misses", str(s["misses"]))
    table.add_row("Hit Rate", f"{s['hit_rate']:.1%}")

    console.print(table)

    if s["by_model"]:
        model_table = Table(title="Entries by Model")
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Count", style="green")

        for model, count in sorted(s["by_model"].items()):
            model_table.add_row(model, str(count))

        console.print()
        console.print(model_table)


@cli.command()
@click.option("--older-than", type=int, help="Only clear entries older than N days")
@click.option("--cache-path", type=click.Path(), help="Path to cache database")
@click.confirmation_option(prompt="Are you sure you want to clear the cache?")
def clear(older_than, cache_path):
    """Clear the cache."""
    cache_path = Path(cache_path) if cache_path else None
    cache = Cache(path=cache_path)

    cache.clear(older_than_days=older_than)

    if older_than:
        console.print(f"[green]Cleared entries older than {older_than} days[/green]")
    else:
        console.print("[green]Cache cleared[/green]")


@cli.command()
@click.argument("output", type=click.Path())
@click.option("--cache-path", type=click.Path(), help="Path to cache database")
def export(output, cache_path):
    """Export the cache database."""
    cache_path = Path(cache_path) if cache_path else None
    cache = Cache(path=cache_path)

    cache.export_db(Path(output))
    console.print(f"[green]Exported cache to {output}[/green]")


@cli.command("import")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--cache-path", type=click.Path(), help="Path to cache database")
@click.confirmation_option(prompt="This will overwrite the current cache. Continue?")
def import_cache(input_file, cache_path):
    """Import a cache database."""
    cache_path = Path(cache_path) if cache_path else None
    cache = Cache(path=cache_path)

    cache.import_db(Path(input_file))
    console.print(f"[green]Imported cache from {input_file}[/green]")


def main():
    cli()


if __name__ == "__main__":
    main()
