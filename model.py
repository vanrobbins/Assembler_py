"""
Model class for the Assembler application.
Handles data management and business logic.
"""

class AssemblerModel:
    def __init__(self):
        self.target_file = ""
        self.status = "Ready"
        self.is_running = False
    
    def set_file(self, file_path):
        """Set the target file path"""
        self.target_file = file_path
        self.status = f"Loaded: {file_path}"
    
    def get_file(self):
        """Get the current target file path"""
        return self.target_file
    
    def get_status(self):
        """Get the current status"""
        return self.status
    
    def set_status(self, status):
        """Set the current status"""
        self.status = status
    
    def is_file_loaded(self):
        """Check if a file is loaded"""
        return bool(self.target_file.strip())
    
    def assemble(self):
        """
        Perform the assembly process.
        Returns True if successful, False otherwise.
        """
        if not self.is_file_loaded():
            self.status = "No file selected to run"
            return False
        
        self.is_running = True
        self.status = "Running assembly..."
        
        try:
            # Add your actual assembly logic here
            # For now, this is a placeholder
            self.status = f"Assembly completed for: {self.target_file}"
            return True
        except Exception as e:
            self.status = f"Assembly failed: {str(e)}"
            return False
        finally:
            self.is_running = False
    
    def clear_file(self):
        """Clear the currently loaded file"""
        self.target_file = ""
        self.status = "No file selected"
