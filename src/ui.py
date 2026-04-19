from .models import PetState


def get_pet_ascii(pet: PetState) -> str:
    """Возвращает ASCII-артику питомца в зависимости от состояния"""
    health = pet.health
    mood = pet.mood

    if health <= 20 or mood >= 80:
        # Плохое состояние
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
  (грустит...)
"""
    elif health >= 80 and mood <= 30:
        # Отличное состояние
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
   (счастлив!)
"""
    elif health >= 50:
        # Нормальное
        return r"""
   /_/\  
  ( o.o ) 
   > ^ <  
"""
    else:
        # Среднее/устал
        return r"""
   /_/\  
  ( -.- ) 
   > ^ <  
"""
