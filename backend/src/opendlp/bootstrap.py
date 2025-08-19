from sqlalchemy.orm import sessionmaker

from opendlp.adapters import database
from opendlp.config import get_db_uri
from opendlp.service_layer import unit_of_work


def bootstrap(
    start_orm: bool = True,
    uow: unit_of_work.AbstractUnitOfWork | None = None,
    session_factory: sessionmaker | None = None,
) -> unit_of_work.AbstractUnitOfWork:
    if start_orm:
        database.start_mappers()

    if session_factory is None:
        session_factory = database.create_session_factory(get_db_uri())

    if uow is None:
        uow = unit_of_work.SqlAlchemyUnitOfWork(session_factory)

    return uow
