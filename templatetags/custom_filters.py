from django import template

register = template.Library()

@register.filter
def get_response_for(responses, user_input):
    # Assuming `responses` is a list of dictionaries where each dictionary
    # represents a conversation with a 'user_input' key and an 'assistant_response' key
    for response in responses:
        if response['user_input'] == user_input:
            return response['assistant_response']
    return "No response found."
