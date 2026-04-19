import sys
from argparse import ArgumentParser

from .models import PetState
from .storage import Storage
from .github_integration import GitHubEvents
from .ui import get_pet_ascii


RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"


def main():
    parser = ArgumentParser(prog="gittama", description="GitTama terminal tamagotchi")
    subparsers = parser.add_subparsers(dest="command", help="Available Commands")

    subparsers.add_parser("status", help="Show the status")
    subparsers.add_parser("log", help="Show event history")

    feed = subparsers.add_parser("feed", help="To feed")
    feed.add_argument("-a", "--amount", type=int, default=15)

    play = subparsers.add_parser("play", help="To play")
    play.add_argument("-a", "--amount", type=int, default=15)

    subparsers.add_parser("sleep", help="Sleep")
    subparsers.add_parser("clean", help="Clean")

    event_parser = subparsers.add_parser("event", help="GitHub-event")
    event_parser.add_argument("type", choices=["commit", "pr", "issue", "ci_success"])

    args = parser.parse_args()

    storage = Storage()
    pet = storage.load()
    pet.update_from_time()

    if args.command == "status" or args.command is None:
        print(get_pet_ascii(pet))
        print(f"{BOLD} GitTama{RESET}")
        print(f"Name:{pet.name}")
        print(f"Hunger:{RED}{pet.hunger:3}{RESET} (0 = full, 100 = hungry)")
        print(f"Energy:{YELLOW}{pet.energy:3}{RESET} (0 = cheerful, 100 = tired)")
        print(f"Mood:{MAGENTA}{pet.mood:3}{RESET} (0 = happy, 100 = sad)")
        print(f"Health:{GREEN}{pet.health:3}{RESET} (0 = bad, 100 = excellent)")

        if pet.achievements:
            print(f"\n{YELLOW} Achievements:{RESET}")
            for ach in pet.achievements:
                print(f"   • {ach}")

        if pet.events_log:
            print(f"\n{BOLD} Recent events:{RESET}")
            for entry in pet.events_log[-5:]:
                print(f"   {entry}")

    elif args.command == "log":
        print(f"{BOLD} Full event history:{RESET}")
        for entry in pet.events_log or ["Nothing has happened yet..."]:
            print(entry)

    elif args.command == "feed":
        pet.hunger = max(0, pet.hunger - args.amount)
        pet.add_event (f "  Fed {args.amount}")
        print (f " {GREEN} Fed {args.amount}!{RESET}")

    elif args.command == "play":
        pet.mood = max(0, pet.mood - args.amount)
        pet.energy = max(0, pet.energy - 5)
        pet.add_event("Played")
        print(f"{CYAN} Let's play!{RESET}")

    elif args.command == "sleep":
        pet.energy = max(0, pet.energy - 40)
        pet.add_event("The pet slept well")
        print(f"{BLUE}The pet slept well!{RESET}")

    elif args.command == "clean":
        pet.health = min(100, pet.health + 10)
        pet.add_event("Repository cleaned")
        print(f"{GREEN} Repository cleaned!{RESET}")

    elif args.command == "event":
        message = GitHubEvents.apply_event(pet, args.type)
        pet.add_event(message)
        pet.check_achievements()
        print(f"{MAGENTA}📡 {message}{RESET}")

    storage.save(pet)


if __name__ == "__main__":
    main()
