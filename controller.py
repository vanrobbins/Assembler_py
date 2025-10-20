"""
Controller class for the Assembler application.
Handles user interactions and coordinates between Model and View.
"""

from model import AssemblerModel
from view import AssemblerView


class AssemblerController:
    def __init__(self):
        self.model = AssemblerModel()
        self.view = AssemblerView()
        
        # Set up view callbacks
        self.view.set_load_callback(self.handle_load_file)
        self.view.set_assemble_callback(self.handle_assemble)
        
        # Initialize view with model data
        self.update_view()
    
    def handle_load_file(self):
        """Handle the load file button click"""
        file_path = self.view.show_file_dialog()
        
        if file_path:
            self.model.set_file(file_path)
            self.view.update_status(self.model.get_status())
            self.view.set_button_state("assemble","normal")
        else:
            if not self.model.is_file_loaded():
                self.model.set_status("No file selected")
                self.view.update_status(self.model.get_status())
    
    def handle_assemble(self):
        """Handle the assemble button click"""
        if not self.model.is_file_loaded():
            self.model.set_status("No file selected to run")
            self.view.update_status(self.model.get_status())
            return
        
        # Disable assemble button during processing
        self.view.set_button_state("assemble", "disabled")
        
        # Perform assembly
        success = self.model.assemble()
        
        # Update view with results
        self.view.update_status(self.model.get_status())
        
        # Re-enable assemble button
        self.view.set_button_state("assemble", "normal")
        
        return success
    
    def update_view(self):
        """Update the view with current model state"""
        self.view.update_status(self.model.get_status())
    
    def run(self):
        """Start the application"""
        self.view.run()
    
    def get_model(self):
        """Get reference to the model (for testing or extension)"""
        return self.model
    
    def get_view(self):
        """Get reference to the view (for testing or extension)"""
        return self.view