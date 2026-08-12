// ABOUTME: Sample payloads the service docs console can load into its forms
// ABOUTME: Plain template literals here, where the inline script had to escape every Jinja brace

export const IMPORT_RESPONDENTS_CSV = `external_id,name,email,gender,age_group,consent,eligible
R001,Alice Smith,alice@example.com,Female,18-30,true,true
R002,Bob Johnson,bob@example.com,Male,31-50,true,true
R003,Carol Williams,carol@example.com,Female,51+,true,true
R004,David Brown,david@example.com,Male,18-30,true,true
R005,Eve Davis,eve@example.com,Female,31-50,true,true`;

export const IMPORT_TARGETS_CSV = `feature,value,min,max,min_flex,max_flex
Gender,Male,3,7,0,2
Gender,Female,3,7,0,2
Age,18-30,2,5,1,1
Age,31-50,2,5,1,1
Age,51+,2,5,1,1`;

// The braces are the point of these two - they show the placeholders an auto-reply
// template can use. In the template this file replaced they had to be written as
// {{ '{{' }}, which made the samples unreadable as the thing they are examples of.
export const EMAIL_SUBJECT = `Thanks for registering, {{ respondent.first_name_or_friend }}!`;

export const EMAIL_BODY = `<p>Hi {{ respondent.first_name_or_friend }},</p>
<p>Thanks for registering for <strong>{{ assembly.title }}</strong>.</p>
<p>We will get back to you about the assembly on {{ assembly.first_assembly_date }}.</p>
<p>Best wishes,<br>The team</p>`;
