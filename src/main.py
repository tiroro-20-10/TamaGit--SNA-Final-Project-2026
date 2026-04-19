from argparse import ArgumentParser
from rich.console import Console
from models import PetState
from storage import Storage
from github_integration import GitHubEvents
from ui import show_status, console

def main():
    parser = ArgumentParser(
        prog="gittama",
        description="GitTama — Terminal Tamagotchi for GitHub and DevOps habits"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("status", help="Show pet status and daily quest")
    subparsers.add_parser("log", help="Show event history")
    subparsers.add_parser("quest", help="Complete today's daily quest")

    feed = subparsers.add_parser("feed", help="Feed the pet")
    feed.add_argument("-a", "--amount", type=int, default=20, help="Amount to feed")

    play = subparsers.add_parser("play", help="Play with the pet")
    play.add_argument("-a", "--amount", type=int, default=15, help="Amount to play")

    subparsers.add_parser("sleep", help="Put the pet to sleep")
    subparsers.add_parser("clean", help="Clean the repository")

    event_parser = subparsers.add_parser("event", help="Simulate GitHub event")
    event_parser.add_argument(
        "type",
        choices=["commit", "pr", "issue", "ci_success"],
        help="Type of GitHub event"
    )

    args = parser.parse_args()

    storage = Storage()
    pet: PetState = storage.load()
    pet.update_from_time()

    if args.command in (None, "status"):
        pet.get_daily_quest()
        show_status(pet)

    elif args.command == "quest":
        pet.complete_quest()
        console.print("[bold green]Quest completed successfully![/bold green]")
        show_status(pet)

    elif args.command == "feed":
        pet.hunger = max(0, pet.hunger - args.amount)
        pet.add_event(f"Fed pet (+{args.amount} hunger)")
        console.print("[green]Pet has been fed![/green]")
        show_status(pet)

    elif args.command == "play":
        pet.mood = max(0, pet.mood - args.amount)
        pet.energy = max(0, pet.energy - 5)
        pet.add_event("Played with pet")
        console.print("[cyan]Played with pet! Mood improved[/cyan]")
        show_status(pet)

    elif args.command == "sleep":
        pet.energy = max(0, pet.energy - 40)
        pet.add_event("Pet slept")
        console.print("[blue]Pet had a good rest![/blue]")
        show_status(pet)

    elif args.command == "clean":
        pet.health = min(100, pet.health + 15)
        pet.add_event("Repository cleaned")
        console.print("[green]Repository is clean now![/green]")
        show_status(pet)

    elif args.command == "event":
        message = GitHubEvents.apply_event(pet, args.type)
        pet.add_event(message)
        pet.check_achievements()
        console.print(f"[magenta]GitHub event processed: {message}[/magenta]")
        show_status(pet)

    elif args.command == "log":
        console.print("[bold]Event History:[/bold]")
        if not pet.events_log:
            console.print("[dim]No events yet...[/dim]")
        else:
            for entry in pet.events_log:
                console.print(entry)

    storage.save(pet)

if __name__ == "__main__":
    main()
