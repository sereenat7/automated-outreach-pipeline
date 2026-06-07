from rich.console import Console

console = Console()


def info(message: str) -> None:
    console.print(f"[bold blue]→[/bold blue] {message}")


def success(message: str) -> None:
    console.print(f"[bold green]✓[/bold green] {message}")


def warn(message: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {message}")


def error(message: str) -> None:
    console.print(f"[bold red]✗[/bold red] {message}")
