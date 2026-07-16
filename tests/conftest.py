import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from ai_project_engineer.database import Base, get_db, make_engine
from ai_project_engineer.main import app
from ai_project_engineer.seed import seed_database

@pytest.fixture
def db(tmp_path):
    engine=make_engine(f"sqlite:///{(tmp_path/'test.db').as_posix()}");Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    with Session() as session:
        yield session
    engine.dispose()

@pytest.fixture
def seeded_db(db):
    seed_database(db);return db

@pytest.fixture
def client(seeded_db):
    def override():yield seeded_db
    app.dependency_overrides[get_db]=override
    with TestClient(app) as c:yield c
    app.dependency_overrides.clear()

