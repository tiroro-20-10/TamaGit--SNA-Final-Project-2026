import sys
from argparse import ArgumentParser

from .models import PetState
from .storage import Storage
from .github_integration import GitHubEvents
from .ui import get_pet_ascii


# Простые ANSI-цвета (работают в любом терминале)
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"


def main():
    parser = ArgumentParser(prog="gittama", description="🐱 GitTama — терминальный тамагочи")
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    subparsers.add_parser("status", help="Показать состояние")
    subparsers.add_parser("log", help="Показать историю событий")

    feed = subparsers.add_parser("feed", help="Покормить")
    feed.add_argument("-a", "--amount", type=int, default=15)

    play = subparsers.add_parser("play", help="Поиграть")
    play.add_argument("-a", "--amount", type=int, default=15)

    subparsers.add_parser("sleep", help="Поспать")
    subparsers.add_parser("clean", help="Почистить")

    event_parser = subparsers.add_parser("event", help="GitHub-событие")
    event_parser.add_argument("type", choices=["commit", "pr", "issue", "ci_success"])

    args = parser.parse_args()

    storage = Storage()
    pet = storage.load()
    pet.update_from_time()

    if args.command == "status" or args.command is None:
        print(get_pet_ascii(pet))
        print(f"{BOLD}🐱 GitTama{RESET}")
        print(f"Имя:        {pet.name}")
        print(f"Голод:      {RED}{pet.hunger:3}{RESET}  (0 = сыт, 100 = голодный)")
        print(f"Энергия:    {YELLOW}{pet.energy:3}{RESET}  (0 = бодрый, 100 = усталый)")
        print(f"Настроение: {MAGENTA}{pet.mood:3}{RESET}  (0 = счастливый, 100 = грустный)")
        print(f"Здоровье:   {GREEN}{pet.health:3}{RESET}  (0 = плохо, 100 = отлично)")

        if pet.achievements:
            print(f"\n{YELLOW}🏆 Достижения:{RESET}")
            for ach in pet.achievements:
                print(f"   • {ach}")

        if pet.events_log:
            print(f"\n{BOLD}📜 Последние события:{RESET}")
            for entry in pet.events_log[-5:]:
                print(f"   {entry}")

    elif args.command == "log":
        print(f"{BOLD}📜 Полная история событий:{RESET}")
        for entry in pet.events_log or ["Пока ничего не происходило..."]:
            print(entry)

    elif args.command == "feed":
        pet.hunger = max(0, pet.hunger - args.amount)
        pet.add_event(f"🍎 Покормили на {args.amount}")
        print(f"{GREEN}🍎 Покормили на {args.amount}!{RESET}")

    elif args.command == "play":
        pet.mood = max(0, pet.mood - args.amount)
        pet.energy = max(0, pet.energy - 5)
        pet.add_event("🎾 Поиграли")
        print(f"{CYAN}🎾 Поиграли!{RESET}")

    elif args.command == "sleep":
        pet.energy = max(0, pet.energy - 40)
        pet.add_event("😴 Питомец выспался")
        print(f"{BLUE}😴 Питомец отлично выспался!{RESET}")

    elif args.command == "clean":
        pet.health = min(100, pet.health + 10)
        pet.add_event("🧹 Репозиторий почищен")
        print(f"{GREEN}🧹 Репозиторий почищен!{RESET}")

    elif args.command == "event":
        message = GitHubEvents.apply_event(pet, args.type)
        pet.add_event(message)
        pet.check_achievements()
        print(f"{MAGENTA}📡 {message}{RESET}")

    storage.save(pet)


if __name__ == "__main__":
    main()
