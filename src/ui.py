from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from models import PetState

console = Console()

ASCII_ARTS = {
    "excellent": r"""
   /_/\  
  ( o.o ) 
   > ^ <   ★ PERFECT!
""",
    "happy": r"""
   /_/\  
  ( o.o ) 
   > ^ <   :)
""",
    "neutral": r"""
   /_/\  
  ( o.o ) 
   > ^ <  
""",
    "tired": r"""
   /_/\  
  ( -.- ) 
   > ^ <   zzz...
""",
    "hungry": r"""
   /_/\  
  ( o.o ) 
   > ^ <   hungry...
""",
    "sad": r"""
   /_/\  
  ( o.o ) 
   > ^ <   :(
""",
    "critical": r"""
   /_/\  
  ( x.x ) 
   > ^ <   CRITICAL...
"""
}

def get_pet_ascii(pet: PetState) -> str:
    if pet.health <= 20 or pet.mood >= 80:
        return ASCII_ARTS["critical"]
    elif pet.health >= 90 and pet.mood <= 20:
        return ASCII_ARTS["excellent"]
    elif pet.mood <= 30:
        return ASCII_ARTS["happy"]
    elif pet.energy >= 80:
        return ASCII_ARTS["tired"]
    elif pet.hunger >= 80:
        return ASCII_ARTS["hungry"]
    elif pet.health >= 70:
        return ASCII_ARTS["neutral"]
    else:
        return ASCII_ARTS["sad"]

def show_status(pet: PetState):
    console.print(Panel(get_pet_ascii(pet), title="GitTama", border_style="blue"))

    table = Table(title="Pet Status", show_header=False)
    table.add_row("Hunger",   f"[red]{pet.hunger:3}[/red]   (0 = full)")
    table.add_row("Energy",   f"[yellow]{pet.energy:3}[/yellow]   (0 = energetic)")
    table.add_row("Mood",     f"[magenta]{pet.mood:3}[/magenta]   (0 = happy)")
    table.add_row("Health",   f"[green]{pet.health:3}[/green]   (100 = perfect)")
    console.print(table)

    if pet.current_quest:
        console.print(Panel(f"[bold yellow]Daily Quest:[/bold yellow] {pet.current_quest}", border_style="yellow"))

    if pet.achievements:
        console.print("[bold yellow]Achievements:[/bold yellow]")
        for ach in pet.achievements:
            console.print(f"   • {ach}")
