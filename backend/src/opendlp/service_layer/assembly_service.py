"""ABOUTME: Assembly management service layer for handling assembly operations
ABOUTME: Provides functions for assembly creation, updates, permissions, and lifecycle management"""

import uuid
from datetime import date
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyStatus

from .exceptions import InsufficientPermissions
from .permissions import can_manage_assembly, can_view_assembly, has_global_organiser
from .unit_of_work import AbstractUnitOfWork
from .user_service import get_user_assemblies


def create_assembly(
    uow: AbstractUnitOfWork,
    title: str,
    created_by_user_id: uuid.UUID,
    question: str = "",
    first_assembly_date: date | None = None,
) -> Assembly:
    """
    Create a new assembly.

    Args:
        uow: Unit of Work for database operations
        title: Assembly title (required)
        created_by_user_id: ID of user creating the assembly
        question: Assembly question (optional, defaults to empty string)
        first_assembly_date: Date of first assembly meeting (optional)

    Returns:
        Created Assembly instance

    Raises:
        InsufficientPermissions: If user cannot create assemblies
        ValueError: If user not found or invalid data
    """
    with uow:
        user = uow.users.get(created_by_user_id)
        if not user:
            raise ValueError(f"User {created_by_user_id} not found")

        # Check permissions - only global organisers and admins can create assemblies
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="create assembly", required_role="global-organiser or admin")

        # Create the assembly
        assembly = Assembly(
            title=title,
            question=question,
            first_assembly_date=first_assembly_date,
        )

        uow.assemblies.add(assembly)
        uow.commit()
        detached_assembly = assembly.create_detached_copy()
        return detached_assembly


def update_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    **updates: Any,
) -> Assembly:
    """
    Update an assembly with new data.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to update
        user_id: ID of user performing the update

    Returns:
        Updated Assembly instance

    Raises:
        ValueError: If assembly or user not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update assembly", required_role="assembly-manager, global-organiser or admin"
            )

        # Apply updates
        for field, value in updates.items():
            if hasattr(assembly, field):
                setattr(assembly, field, value)

        uow.commit()
        # Explicit typing to satisfy mypy
        updated_assembly: Assembly = assembly
        return updated_assembly


def get_assembly_with_permissions(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Assembly:
    """
    Get an assembly if user has permission to view it.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to retrieve
        user_id: ID of user requesting the assembly

    Returns:
        Assembly instance

    Raises:
        ValueError: If assembly or user not found
        InsufficientPermissions: If user cannot view this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view assembly", required_role="assembly role or global privileges")

        # Explicit typing to satisfy mypy
        retrieved_assembly: Assembly = assembly.create_detached_copy()
        return retrieved_assembly


def archive_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Assembly:
    """
    Archive an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to archive
        user_id: ID of user performing the archival

    Returns:
        Archived Assembly instance

    Raises:
        ValueError: If assembly or user not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="archive assembly", required_role="assembly-manager, global-organiser or admin"
            )

        # Archive the assembly
        assembly.status = AssemblyStatus.ARCHIVED

        uow.commit()
        # Explicit typing to satisfy mypy
        archived_assembly: Assembly = assembly
        return archived_assembly


def get_user_accessible_assemblies(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
) -> list[Assembly]:
    """
    Get all assemblies that a user has access to.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to get assemblies for

    Returns:
        List of assemblies user can access

    Raises:
        ValueError: If user not found
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Use existing user_service function for consistency

        return get_user_assemblies(uow, user_id)
