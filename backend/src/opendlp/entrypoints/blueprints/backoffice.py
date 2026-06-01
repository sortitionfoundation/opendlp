"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes for dashboard, assembly CRUD, data source, and team members"""

import base64
import io
import uuid
from typing import cast

import qrcode
from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.registration_page import (
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.domain.validators import SlugError
from opendlp.domain.value_objects import AssemblyRole
from opendlp.entrypoints.forms import (
    AddUserToAssemblyForm,
    CreateAssemblyForm,
    CreateAssemblyGSheetForm,
    DbSelectionSettingsForm,
    EditAssemblyForm,
    EditAssemblyGSheetForm,
)
from opendlp.service_layer.assembly_service import (
    create_assembly,
    get_assembly_nav_context,
    get_assembly_with_permissions,
    get_or_create_csv_config,
    get_or_create_selection_settings,
    update_assembly,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    generate_starter_form_html,
    get_registration_page_with_source,
    publish_registration_page,
    reopen_registration_page,
    unpublish_registration_page,
    update_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.respondent_service import get_respondent_attribute_columns
from opendlp.service_layer.user_service import (
    get_assembly_members,
    get_user_assemblies,
    grant_user_assembly_role,
    revoke_user_assembly_role,
    search_assembly_candidate_users,
)
from opendlp.translations import gettext as _

backoffice_bp = Blueprint("backoffice", __name__)


def generate_qr_code_base64(url: str) -> str:
    """Generate a QR code for the given URL and return it as a base64-encoded PNG data URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer)  # qrcode images always save as PNG
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"


def generate_qr_code_png(url: str) -> bytes:
    """Generate a QR code for the given URL and return it as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer)  # qrcode images always save as PNG
    buffer.seek(0)
    return buffer.getvalue()


@backoffice_bp.route("/showcase")
def showcase() -> ResponseReturnValue:
    """Component showcase page demonstrating the backoffice design system."""
    return render_template("backoffice/showcase.html"), 200


@backoffice_bp.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    """Backoffice dashboard showing user's assemblies."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("backoffice/dashboard.html", assemblies=assemblies), 200
    except Exception as e:
        current_app.logger.error(f"Backoffice dashboard error for user {current_user.id}: {e}")
        return render_template("backoffice/dashboard.html", assemblies=[]), 500


@backoffice_bp.route("/assembly/new", methods=["GET", "POST"])
@login_required
def new_assembly() -> ResponseReturnValue:
    """Create a new assembly in backoffice."""
    form = CreateAssemblyForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                assembly = create_assembly(
                    uow=uow,
                    title=form.title.data or "",
                    created_by_user_id=current_user.id,
                    question=form.question.data or "",
                    first_assembly_date=form.first_assembly_date.data,
                    number_to_select=form.number_to_select.data or 0,
                )

            flash(_("Assembly '%(title)s' created successfully", title=assembly.title), "success")
            return redirect(url_for("backoffice.view_assembly", assembly_id=assembly.id))
        except InsufficientPermissions as e:
            current_app.logger.warning(f"Insufficient permissions to create assembly for user {current_user.id}: {e}")
            flash(_("You don't have permission to create assemblies"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except NotFoundError as e:
            current_app.logger.error(f"User not found during assembly creation for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except Exception as e:
            current_app.logger.error(f"Create assembly error for user {current_user.id}: {e}")
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))

    return render_template("backoffice/create_assembly.html", form=form), 200


@backoffice_bp.route("/assembly/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly details page."""
    try:
        nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        # Get registration page data from service layer
        uow = bootstrap.bootstrap()
        reg_result = get_registration_page_with_source(uow, current_user.id, assembly_id)
        registration_page = reg_result[0] if reg_result else None

        # Generate QR code for the short URL if registration page has a short slug
        qr_code_data_url = None
        if registration_page and registration_page.short_url_slug:
            short_url = request.host_url + "r/" + registration_page.short_url_slug
            qr_code_data_url = generate_qr_code_base64(short_url)

        return render_template(
            "backoffice/assembly_details.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            registration_page=registration_page,
            qr_code_data_url=qr_code_data_url,
        ), 200
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Backoffice assembly error for user {current_user.id}: {e}")
        flash(_("An error occurred while loading the assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice edit assembly page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        form = EditAssemblyForm(obj=assembly)

        # Get registration page data from service layer
        reg_result = get_registration_page_with_source(uow, current_user.id, assembly_id)
        registration_page = reg_result[0] if reg_result else None

        if form.validate_on_submit():
            try:
                # Extract URL slug data from form (not part of WTForms, added as extra fields)
                url_slug = request.form.get("url_slug", "").strip()
                short_url_slug = request.form.get("short_url_slug", "").strip()

                uow2 = bootstrap.bootstrap()
                with uow2:
                    updated_assembly = update_assembly(
                        uow=uow2,
                        assembly_id=assembly_id,
                        user_id=current_user.id,
                        title=form.title.data,
                        question=form.question.data or "",
                        first_assembly_date=form.first_assembly_date.data,
                        number_to_select=form.number_to_select.data,
                    )

                # Save URL slugs via registration page service if registration page exists
                if registration_page and (url_slug or short_url_slug):
                    uow3 = bootstrap.bootstrap()
                    update_registration_page(
                        uow=uow3,
                        user_id=current_user.id,
                        assembly_id=assembly_id,
                        url_slug=url_slug if url_slug else None,
                        short_url_slug=short_url_slug if short_url_slug else None,
                    )

                flash(_("Assembly '%(title)s' updated successfully", title=updated_assembly.title), "success")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except SlugError as e:
                current_app.logger.warning(f"Slug error editing assembly {assembly_id}: {e}")
                flash(_("The URL slug '%(slug)s' is already in use", slug=str(e)), "error")
                # Re-render form with error
                return render_template(
                    "backoffice/edit_assembly.html",
                    form=form,
                    assembly=assembly,
                    registration_page=registration_page,
                ), 200
            except InsufficientPermissions as e:
                current_app.logger.warning(
                    f"Insufficient permissions to edit assembly {assembly_id} for user {current_user.id}: {e}"
                )
                flash(_("You don't have permission to edit this assembly"), "error")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except NotFoundError as e:
                current_app.logger.error(
                    f"Assembly or user not found while editing assembly {assembly_id} user {current_user.id}: {e}"
                )
                flash(_("An error occurred while updating the assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))
            except Exception as e:
                current_app.logger.error(f"Edit assembly error for assembly {assembly_id} user {current_user.id}: {e}")
                flash(_("An error occurred while updating the assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))

        return render_template(
            "backoffice/edit_assembly.html",
            form=form,
            assembly=assembly,
            registration_page=registration_page,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for edit by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to access assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/update-number-to-select", methods=["POST"])
@login_required
def update_number_to_select(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Update just the number_to_select field for an assembly."""
    try:
        number_to_select = request.form.get("number_to_select", type=int)
        if number_to_select is None or number_to_select < 1:
            flash(_("Please enter a valid positive number"), "error")
            return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, edit_number=1))

        uow = bootstrap.bootstrap()
        with uow:
            updated_assembly = update_assembly(
                uow=uow,
                assembly_id=assembly_id,
                user_id=current_user.id,
                number_to_select=number_to_select,
            )

        flash(_("Number to select updated to %(number)s", number=updated_assembly.number_to_select), "success")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to update number_to_select for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for update by user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly data page."""
    try:
        google_service_account_email = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "UNKNOWN")

        nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        # Get selection settings for gsheet display and form population
        sel_settings = None
        try:
            uow_sel = bootstrap.bootstrap()
            sel_settings = get_or_create_selection_settings(uow_sel, current_user.id, assembly_id)
        except Exception as sel_error:
            current_app.logger.error(f"Error loading selection settings: {sel_error}")

        # Set up gsheet form if gsheet source is selected
        gsheet_mode = "new"
        gsheet_form = None
        if nav.data_source == "gsheet":
            mode_param = request.args.get("mode", "")
            gsheet_mode = ("edit" if mode_param == "edit" else "view") if nav.gsheet else "new"
            if nav.gsheet:
                gsheet_form = EditAssemblyGSheetForm(
                    obj=nav.gsheet,
                    id_column=sel_settings.id_column if sel_settings else "",
                    check_same_address=sel_settings.check_same_address if sel_settings else True,
                    check_same_address_cols_string=sel_settings.check_same_address_cols_string if sel_settings else "",
                    columns_to_keep_string=sel_settings.columns_to_keep_string if sel_settings else "",
                )
            else:
                gsheet_form = CreateAssemblyGSheetForm()

        # Set up CSV settings form if CSV source is selected
        csv_settings_form = None
        csv_available_columns: list[str] = []
        csv_mode = "view"  # Default to view mode
        csv_config = None
        if nav.data_source == "csv":
            # Determine mode (view or edit)
            mode_param = request.args.get("mode", "")
            csv_mode = "edit" if mode_param == "edit" else "view"

            # Get or create CSV config
            uow_csv_config = bootstrap.bootstrap()
            with uow_csv_config:
                csv_config = get_or_create_csv_config(uow_csv_config, current_user.id, assembly_id)

                # Get available columns from respondents for validation hints
                csv_available_columns = get_respondent_attribute_columns(uow_csv_config, assembly_id)

            # Create form with current values from SelectionSettings
            csv_settings_form = DbSelectionSettingsForm(
                data={
                    "check_same_address": sel_settings.check_same_address if sel_settings else True,
                    "check_same_address_cols_string": sel_settings.check_same_address_cols_string
                    if sel_settings
                    else "",
                    "columns_to_keep_string": sel_settings.columns_to_keep_string if sel_settings else "",
                },
                available_columns=csv_available_columns,
            )

        return render_template(
            "backoffice/assembly_data.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            data_source_locked=nav.data_source_locked,
            gsheet=nav.gsheet,
            selection_settings=sel_settings,
            gsheet_mode=gsheet_mode,
            gsheet_form=gsheet_form,
            google_service_account_email=google_service_account_email,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            csv_status=nav.csv_status,
            csv_settings_form=csv_settings_form,
            csv_available_columns=csv_available_columns,
            csv_mode=csv_mode,
            csv_config=csv_config,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly data error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly data"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/registration")
@login_required
def view_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice registration form configuration page."""
    try:
        nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        # Get registration page and HTML source from service layer
        uow = bootstrap.bootstrap()
        result = get_registration_page_with_source(uow, current_user.id, assembly_id)

        # HTML content
        has_registration_page = result is not None
        registration_page = result[0] if result else None
        if result:
            html = cast(RegistrationPageHtml, result[1])
            html_content = html.form_html
            thank_you_html = result[0].thank_you_html
            registration_status = result[0].status.value  # "TEST", "PUBLISHED", or "CLOSED"
        else:
            html_content = ""
            thank_you_html = ""
            registration_status = "TEST"  # Default for new pages

        # Generate QR code from the short URL (only when a short slug is configured)
        qr_code_data_url = None
        if registration_page and registration_page.short_url_slug:
            short_url = request.host_url + "r/" + registration_page.short_url_slug
            qr_code_data_url = generate_qr_code_base64(short_url)

        return render_template(
            "backoffice/assembly_registration.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            registration_page=registration_page,
            qr_code_data_url=qr_code_data_url,
            registration_status=registration_status,
            html_content=html_content,
            thank_you_html=thank_you_html,
            has_registration_page=has_registration_page,
        ), 200
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(
            f"View assembly registration error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("An error occurred while loading registration settings"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _handle_registration_action(action: str, user_id: uuid.UUID, assembly_id: uuid.UUID) -> str:
    """Handle publish/unpublish/close/reopen/save action for registration page. Returns flash message."""
    if action == "publish":
        uow = bootstrap.bootstrap()
        result = get_registration_page_with_source(uow, user_id, assembly_id)
        if result and result[0].status == RegistrationPageStatus.TEST:
            uow = bootstrap.bootstrap()
            publish_registration_page(uow, user_id, assembly_id)
            return _("Registration form published successfully")
        return _("Registration form HTML updated successfully")
    if action == "unpublish":
        uow = bootstrap.bootstrap()
        unpublish_registration_page(uow, user_id, assembly_id)
        return _("Registration form unpublished")
    if action == "close":
        uow = bootstrap.bootstrap()
        close_registration_page(uow, user_id, assembly_id)
        return _("Registration form closed")
    if action == "reopen":
        uow = bootstrap.bootstrap()
        reopen_registration_page(uow, user_id, assembly_id)
        return _("Registration form reopened")
    uow = bootstrap.bootstrap()
    result = get_registration_page_with_source(uow, user_id, assembly_id)
    if result and result[0].status == RegistrationPageStatus.PUBLISHED:
        return _("Registration form saved and republished")
    return _("Registration form saved")


@backoffice_bp.route("/assembly/<uuid:assembly_id>/registration/save", methods=["POST"])
@login_required
def save_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save and publish registration form HTML content."""
    try:
        # Verify user has permission to access this assembly (side effect: raises if unauthorized)
        _nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            "",
        )

        html_content = request.form.get("html_content", "")
        action = request.form.get("action", "save")

        # Update HTML content (will raise RegistrationPageNotFoundError if page doesn't exist)
        uow = bootstrap.bootstrap()
        update_registration_page_html(uow, current_user.id, assembly_id, html_content)

        flash_message = _handle_registration_action(action, current_user.id, assembly_id)
        flash(flash_message, "success")
        return redirect(url_for("backoffice.view_assembly_registration", assembly_id=assembly_id))
    except RegistrationPageNotReady as e:
        # Show specific validation errors for publishing
        error_message = "; ".join(e.problems)
        current_app.logger.warning(f"Registration page not ready for assembly {assembly_id}: {error_message}")
        flash(error_message, "error")
        return redirect(url_for("backoffice.view_assembly_registration", assembly_id=assembly_id))
    except RegistrationPageNotFoundError:
        # Registration page doesn't exist yet - redirect to Details tab to create it
        flash(_("Please create a registration page first from the Details tab."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except ValueError as e:
        current_app.logger.warning(f"Validation error for assembly {assembly_id}: {e}")
        flash(str(e), "error")
        return redirect(url_for("backoffice.view_assembly_registration", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Save assembly registration error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        current_app.logger.exception("Full traceback:")
        flash(_("An error occurred while saving registration settings"), "error")
        return redirect(url_for("backoffice.view_assembly_registration", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/registration/create", methods=["POST"])
@login_required
def create_assembly_registration_page(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create a registration page with auto-generated slugs from the assembly name."""
    try:
        uow = bootstrap.bootstrap()
        create_registration_page_with_slugs(uow, current_user.id, assembly_id)
        flash(
            _("Registration page created. URLs have been generated automatically and can be edited below."),
            "success",
        )
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except ValueError as e:
        # Already has a registration page
        current_app.logger.warning(f"Cannot create registration page for assembly {assembly_id}: {e}")
        flash(_("This assembly already has a registration page."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Error creating registration page for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full traceback:")
        flash(_("An error occurred while creating the registration page"), "error")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/registration/skeleton")
@login_required
def get_registration_skeleton(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Generate starter HTML form skeleton based on assembly's field definitions."""
    try:
        uow = bootstrap.bootstrap()
        html = generate_starter_form_html(uow, current_user.id, assembly_id)
        return jsonify({"html": html})
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to access this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        current_app.logger.error(f"Generate skeleton error for assembly {assembly_id}: {e}")
        return jsonify({"error": _("An error occurred while generating the form skeleton")}), 500


@backoffice_bp.route("/assembly/<uuid:assembly_id>/registration/qr-code.png")
@login_required
def download_registration_qr_code(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Download registration QR code as PNG image."""
    try:
        # Verify user has permission to access this assembly
        _nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            "",
        )

        # TODO: Get real short URL from service layer when available
        # For now, use assembly ID as a placeholder slug
        placeholder_short_url = request.host_url + "r/" + str(assembly_id)[:8]
        qr_png = generate_qr_code_png(placeholder_short_url)

        return Response(
            qr_png,
            mimetype="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="registration-qr-{str(assembly_id)[:8]}.png"',
                "Cache-Control": "no-cache",
            },
        )
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to access this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Download QR code error for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("An error occurred while generating QR code"), "error")
        return redirect(url_for("backoffice.view_assembly_registration", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly team members page."""
    try:
        nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        uow = bootstrap.bootstrap()
        with uow:
            assembly_users = get_assembly_members(uow, assembly_id, current_user)

        can_manage_assembly_users = has_global_admin(current_user)
        add_user_form = AddUserToAssemblyForm()

        return render_template(
            "backoffice/assembly_members.html",
            assembly=nav.assembly,
            assembly_users=assembly_users,
            can_manage_assembly_users=can_manage_assembly_users,
            add_user_form=add_user_form,
            current_tab="members",
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly members error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An error occurred while loading team members"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/add", methods=["POST"])
@login_required
def add_user_to_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a user to an assembly with a specific role."""
    form = AddUserToAssemblyForm()

    try:
        uow = bootstrap.bootstrap()
        with uow:
            if form.validate_on_submit():
                user_id = uuid.UUID(form.user_id.data)

                # Role is already an AssemblyRole enum from form coercion
                role = form.role.data
                assert isinstance(role, AssemblyRole)

                # Get email adapters for sending notification
                email_adapter = get_email_adapter()
                template_renderer = get_template_renderer(current_app)
                url_generator = get_url_generator(current_app)

                # Call service layer to add user to assembly
                _assembly_role, target_user = grant_user_assembly_role(
                    uow=uow,
                    user_id=user_id,
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                    email_adapter=email_adapter,
                    template_renderer=template_renderer,
                    url_generator=url_generator,
                )

                flash(
                    _(
                        "%(user)s added to assembly with role %(role)s",
                        user=target_user.display_name,
                        role=role.value,
                    ),
                    "success",
                )
            else:
                flash(_("Please select a user and role"), "error")

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.error(f"Error adding user to assembly {assembly_id}: {e}")
        flash(_("Could not add user to assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to add user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to add users to this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error adding user to assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while adding the user to the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/<uuid:user_id>/remove", methods=["POST"])
@login_required
def remove_user_from_assembly(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a user from an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Call service layer to remove user from assembly
            _assembly_role, target_user = revoke_user_assembly_role(
                uow=uow,
                user_id=user_id,
                assembly_id=assembly_id,
                current_user=current_user,
            )

            flash(
                _("%(user)s removed from assembly", user=target_user.display_name),
                "success",
            )

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        current_app.logger.error(f"Error removing user from assembly {assembly_id}: {e}")
        flash(_("Could not remove user from assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to remove user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to remove users from this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error removing user from assembly {assembly_id} for user {current_user.id}: {e}"
        )
        flash(_("An error occurred while removing the user from the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/search")
@login_required
def search_users(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Search for users not yet added to the assembly.

    Returns JSON array for use with autocomplete component.
    """
    try:
        search_term = request.args.get("q", "").strip()

        uow = bootstrap.bootstrap()
        matching_users = search_assembly_candidate_users(uow, assembly_id, search_term, current_user)

        # Return JSON array with id, label, sublabel format expected by autocomplete
        results = [
            {
                "id": str(user.id),
                "label": user.email,
                "sublabel": user.display_name,
            }
            for user in matching_users
        ]

        return jsonify(results), 200

    except InsufficientPermissions:
        return jsonify([]), 403
    except Exception as e:
        current_app.logger.error(f"Error searching users for assembly {assembly_id}: {e}")
        return jsonify([]), 500


@backoffice_bp.route("/showcase/search-demo")
def search_demo() -> ResponseReturnValue:
    """Demo search endpoint for showcase page.

    Returns mock data for demonstrating the search_dropdown component.
    """
    search_term = request.args.get("q", "").strip().lower()

    # Mock data for demonstration
    mock_users = [
        {"id": "1", "label": "alice@example.com", "sublabel": "Alice Johnson"},
        {"id": "2", "label": "bob@example.com", "sublabel": "Bob Smith"},
        {"id": "3", "label": "carol@example.com", "sublabel": "Carol Williams"},
        {"id": "4", "label": "david@example.com", "sublabel": "David Brown"},
        {"id": "5", "label": "eve@example.com", "sublabel": "Eve Davis"},
    ]

    if not search_term:
        return jsonify([]), 200

    # Filter mock data based on search term
    results = [
        user for user in mock_users if search_term in user["label"].lower() or search_term in user["sublabel"].lower()
    ]

    return jsonify(results), 200
