"""Identify obsolete entities belonging only to this integration entry."""
from .const import DOMAIN, ENTITY_KEYS


def is_obsolete_entity(entity, entry_id, retained_keys=None):
    prefix = f"{entry_id}_"
    return (
        entity.config_entry_id == entry_id
        and entity.platform == DOMAIN
        and entity.unique_id.startswith(prefix)
        and entity.unique_id[len(prefix):] not in (ENTITY_KEYS if retained_keys is None else retained_keys)
    )
