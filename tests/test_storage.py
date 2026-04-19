import tempfile
from pathlib import Path
from src.models import PetState
from src.storage import Storage

def test_storage_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        storage = Storage(str(path))
        
        pet = PetState(name="TestTama", hunger=30, mood=20)
        storage.save(pet)
        
        loaded = storage.load()
        assert loaded.name == "TestTama"
        assert loaded.hunger == 30
        assert loaded.mood == 20
        print("✅ Тест storage прошёл успешно!")
