from argparse import ArgumentParser
from pathlib import Path

from .git_integration import GitSnapshot, collect_git_snapshot
from .github_integration import GitHubEvents
from .pet_engine import (
    apply_git_snapshot,
    clean,
    feed,
    play,
    sleep,
    summarize_messages,
    update_from_time,
)
from .storage import Storage
from .ui import get_pet_ascii


RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    storage = Storage()
    pet = storage.load()
    update_from_time(pet)

    command = args.command or "status"

    if command == "status":
        print_status(pet)

    elif command == "log":
        print(f"{BOLD}Full event history:{RESET}")
        for entry in pet.events_log or ["Nothing has happened yet..."]:
            print(entry)

    elif command == "feed":
        message = feed(pet, args.amount)
        print(f"{GREEN}{message}!{RESET}")

    elif command == "play":
        message = play(pet, args.amount)
        print(f"{CYAN}{message}!{RESET}")

    elif command == "sleep":
        message = sleep(pet)
        print(f"{BLUE}{message}!{RESET}")

    elif command == "clean":
        message = clean(pet)
        print(f"{GREEN}{message}!{RESET}")

    elif command == "mock-event":
        message = GitHubEvents.apply_mock_event(pet, args.type)
        print(f"{MAGENTA}{message}{RESET}")

    elif command == "scan":
        snapshot = collect_git_snapshot(Path(args.path))
        messages = apply_git_snapshot(pet, snapshot)
        print_scan_result(snapshot, messages)

    storage.save(pet)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="gittama", description="GitTama terminal tamagotchi")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("status", help="Show the pet status")
    subparsers.add_parser("log", help="Show event history")

    feed_parser = subparsers.add_parser("feed", help="Feed the pet")
    feed_parser.add_argument("-a", "--amount", type=int, default=15)

    play_parser = subparsers.add_parser("play", help="Play with the pet")
    play_parser.add_argument("-a", "--amount", type=int, default=15)

    subparsers.add_parser("sleep", help="Let the pet sleep")
    subparsers.add_parser("clean", help="Reward repository cleanup")

    mock_event_parser = subparsers.add_parser("mock-event", help="Apply a simulated GitHub event")
    mock_event_parser.add_argument("type", choices=["commit", "pr", "issue", "issue_closed", "ci_success"])

    scan_parser = subparsers.add_parser("scan", help="Scan a local git repository")
    scan_parser.add_argument("path", nargs="?", default=".", help="Repository path, defaults to current directory")

    return parser


def print_status(pet) -> None:
    print(get_pet_ascii(pet))
    print(f"{BOLD}GitTama{RESET}")
    print(f"Name: {pet.name}")
    print(f"Hunger: {RED}{pet.hunger:3}{RESET} (0 = full, 100 = hungry)")
    print(f"Energy: {YELLOW}{pet.energy:3}{RESET} (0 = cheerful, 100 = tired)")
    print(f"Mood:   {MAGENTA}{pet.mood:3}{RESET} (0 = happy, 100 = sad)")
    print(f"Health: {GREEN}{pet.health:3}{RESET} (0 = bad, 100 = excellent)")

    if pet.achievements:
        print(f"\n{YELLOW}Achievements:{RESET}")
        for achievement in pet.achievements:
            print(f"   - {achievement}")

    if pet.events_log:
        print(f"\n{BOLD}Recent events:{RESET}")
        for entry in pet.events_log[-5:]:
            print(f"   {entry}")


def print_scan_result(snapshot: GitSnapshot, messages: list[str]) -> None:
    if snapshot.is_repo:
        print(f"{BOLD}Git scan:{RESET} {snapshot.repo_root}")
        print(f"Branch: {snapshot.branch}")
        print(f"Dirty: {'yes' if snapshot.is_dirty else 'no'}")
        if snapshot.last_commit_hash:
            print(f"Last commit: {snapshot.last_commit_hash[:8]} {snapshot.last_commit_subject or ''}")
        if snapshot.upstream_available:
            print(f"Unpushed: {snapshot.unpushed_commits}")
            print(f"Unpulled: {snapshot.unpulled_commits}")
        else:
            print("Upstream: not configured")
    else:
        print(f"{YELLOW}Git scan skipped:{RESET} {snapshot.error}")

    print("\nPet reactions:")
    print(summarize_messages(messages))


if __name__ == "__main__":
    main()
