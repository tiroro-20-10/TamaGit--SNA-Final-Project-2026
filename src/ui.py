from .models import PetState


def get_pet_ascii(pet: PetState) -> str:
    health = pet.health
    mood = pet.mood

    if health <= 20 or mood >= 80:
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
  (sad...)
"""
    elif health >= 80 and mood <= 30:
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
   (happy!)
"""
    elif health >= 50:
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
"""
    else:
        return r"""
   /_/\  
  ( -.- ) 
   > ^ <  
"""
