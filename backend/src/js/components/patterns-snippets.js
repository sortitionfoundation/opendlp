// ABOUTME: The copy-to-clipboard code samples shown on the frontend patterns reference page
// ABOUTME: Documentation content, kept apart from the controller so that stays readable

// These were built by string concatenation inside the patterns.html template, where
// every Jinja delimiter needed escaping as {{ "{%" }}. In a .js file they are just
// text, so they are written literally.

export const URL_SELECT_CODE = `<div x-data="urlSelect({
    baseUrl: '$url_for(...)$',
    paramName: 'source',
    initialValue: '$current_value$'
})">
    <select x-model="selected"
            @change="navigate($event)"
            data-focus-id="my-select">
        <option value="">Choose...</option>
        <option value="opt1">Option 1</option>
    </select>
</div>`;

export const INLINE_SELECT_CODE = `// In your Alpine component, declare FLAT property:
Alpine.data('myComponent', () => ({
    assemblyId: '',  // Flat property
    // NOT: form: { assemblyId: '' }  // Nested - won't work with CSP

    executeAction() {
        fetch('/api/endpoint', {
            body: JSON.stringify({ assembly_id: this.assemblyId })
        });
    }
}));

// In template:
<select x-model="assemblyId">
    <option value="">Select...</option>
    {% for a in assemblies %}
        <option value="{{ a.id }}">{{ a.title }}</option>
    {% endfor %}
</select>`;

export const FILE_UPLOAD_TEMPLATE_CODE = `{% from "backoffice/components/input.html" import file_input %}

<form method="post"
      action="{{ url_for('...') }}"
      enctype="multipart/form-data">
    {{ form.hidden_tag() }}

    {{ file_input(
        "csv_file",
        label="CSV File",
        hint="Select a CSV file to upload",
        accept=".csv",
        required=true,
        error=first_error(form.csv_file.errors)
    ) }}

    <button type="submit">Upload</button>
</form>`;

export const FILE_UPLOAD_ROUTE_CODE = `# Flask-WTF Form
class UploadCsvForm(FlaskForm):
    csv_file = FileField(
        _l("CSV File"),
        validators=[
            FileRequired(message=_l("Please select a file")),
            FileAllowed(["csv"], message=_l("Only CSV files allowed")),
        ],
    )

# Route handler
@bp.route("/upload", methods=["POST"])
def upload_csv():
    form = UploadCsvForm()

    if not form.validate_on_submit():
        # Re-render form with errors
        return render_template("...", form=form)

    # Read file content as string
    csv_file = form.csv_file.data
    csv_content = csv_file.read().decode("utf-8-sig")
    filename = csv_file.filename or "unknown.csv"

    # Pass to service layer (content as string, not file)
    result = import_from_csv(uow, csv_content=csv_content)

    flash(_("Imported successfully"), "success")
    return redirect(url_for("..."))`;

export const PROGRESS_BAR_CODE = `{% from "backoffice/components/modal.html" import progress_bar %}

{# Indeterminate spinner (default) #}
{{ progress_bar() }}

{# Indeterminate with custom label #}
{{ progress_bar(label="Loading data...") }}

{# Determinate progress bar #}
{{ progress_bar(
    label="Processing item 50 of 200",
    current=50,
    total=200
) }}

{# With ProgressInfo object, use progress_indicator instead #}
{% from "backoffice/components/modal.html" import progress_indicator %}
{{ progress_indicator(run_record.progress_info) }}`;

export const PAGINATION_TEMPLATE_CODE = `{% from "backoffice/components/pagination.html" import pagination %}

{{ pagination(
    page=page,
    total_pages=total_pages,
    per_page=per_page,
    total_count=total_count,
    base_url=url_for('my.route', assembly_id=assembly.id),
    item_name=_("respondents")
) }}`;

export const PAGINATION_ROUTE_CODE = `@bp.route("/items")
def list_items():
    # Get page from query param, default to 1
    page = request.args.get("page", 1, type=int)
    per_page = 20  # Items per page

    # Paginate query
    items = Item.query.paginate(page=page, per_page=per_page)

    return render_template(
        "items/list.html",
        items=items.items,
        page=page,
        total_pages=items.pages,
        per_page=per_page,
        total_count=items.total,
    )`;

export const SCROLL_PRESERVE_CODE = `{# Add the directive to any container with navigation links #}
<nav class="pagination" x-data="{}" x-scroll-preserve-links>
    <a href="?page=1">1</a>
    <a href="?page=2">2</a>
    <a href="?page=3">3</a>
</nav>

{# The pagination component includes this by default #}
{{ pagination(..., preserve_scroll=true) }}

{# Disable scroll preservation if needed #}
{{ pagination(..., preserve_scroll=false) }}`;

export const PRESERVE_SCROLL_CODE = `{# Link with scroll preservation #}
<a :href="$preserveScroll('/some/url?page=2')">Page 2</a>

{# Form action with scroll preservation #}
<form :action="$preserveScroll('/submit')" method="post">
    ...
</form>

{# Result: URL gets &scroll=1250 appended #}
/some/url?page=2&scroll=1250`;

export const SCROLL_DIRECTIVE_CODE = `{# Container with auto-scroll preservation #}
<nav x-data="{}" x-scroll-preserve-links>
    <a href="?page=1">1</a>  {# scroll preserved #}
    <a href="?page=2">2</a>  {# scroll preserved #}
    <a href="/dashboard" data-no-scroll-preserve>Home</a>  {# opt-out #}
</nav>

{# The pagination component includes this by default #}
{{ pagination(..., preserve_scroll=true) }}`;

export const NAVIGATE_SCROLL_CODE = `{# Filter dropdown WITHOUT scroll preservation #}
<select data-navigate-base-url="{{ url_for('...') }}"
        data-navigate-param="status">
    <option value="">All</option>
    <option value="active">Active</option>
</select>

{# Filter dropdown WITH scroll preservation #}
<select data-navigate-base-url="{{ url_for('...') }}"
        data-navigate-param="status"
        data-navigate-preserve-scroll>
    <option value="">All</option>
    <option value="active">Active</option>
</select>`;
