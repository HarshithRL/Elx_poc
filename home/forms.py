from django import forms

from chat.models import (  # Ensure you import PDFFile
    PDFFile,
    Session,  # Assuming the model is named 'Session'
)


class PDFUploadForm(forms.ModelForm):
    pdf_file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "id": "file-upload",
                "accept": ".pdf",
                "style": "display: none",
                "class": "browse",
                "allow_multiple_selected": True,  # Allow multiple file selection
            }
        ),
        required=False,
    )

    class Meta:
        model = Session
        fields = [
            "pdf_file"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class CloudFileForm(forms.Form):
    # Use a MultipleChoiceField to allow selection of multiple files
    file_choices = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label="Select Files",
        required=True
    )

    def __init__(self, *args, **kwargs):
        # Dynamically populate file choices
        file_choices = kwargs.pop("file_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["file_choices"].choices = file_choices

