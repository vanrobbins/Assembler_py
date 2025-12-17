"""
View class for the Assembler application.
Handles the GUI components and user interface. :P
"""

from tkinter import *
from tkinter import ttk
from tkinter import filedialog


class AssemblerView:
    def __init__(self):
        self.root = None
        self.mainframe = None
        self.title_label = None
        self.load_button = None
        self.run_button = None
        self.status_label = None
        
        # Callback functions (to be set by controller)
        self.on_load_file = None
        self.on_assemble = None
        
        self.setup_gui()
    
    def setup_gui(self):
        """Initialize and configure the GUI components"""
        self.root = Tk()
        self.root.title("Assembler in Python")
        self.root.geometry("600x400")
        
        # Configure the root window's grid so the frame expands
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Create and place the ttk.Frame to fill the root window
        self.mainframe = ttk.Frame(self.root, padding="10")
        self.mainframe.grid(column=0, row=0, sticky="nsew")
        
        # Configure the mainframe's internal grid so buttons expand
        self.mainframe.columnconfigure(0, weight=1)
        self.mainframe.columnconfigure(1, weight=1)
        self.mainframe.rowconfigure(0, weight=1)
        self.mainframe.rowconfigure(1, weight=1)
        self.mainframe.rowconfigure(2, weight=1)
        
        # Create and place GUI components
        self.title_label = ttk.Label(self.mainframe, text="Assembler in Python")
        self.title_label.grid(column=0, row=0, columnspan=2, sticky="ns", padx=5, pady=5)
        
        self.load_button = ttk.Button(self.mainframe, text="Load File", cursor="hand2", 
                                     command=self._on_load_clicked)
        self.load_button.grid(column=0, row=1, sticky="nsew", padx=5, pady=5)
        
        self.run_button = ttk.Button(self.mainframe, text="Assemble", cursor="hand2", 
                                    command=self._on_assemble_clicked, state="disabled")
        self.run_button.grid(column=1, row=1, sticky="nsew", padx=5, pady=5)
        
        self.status_label = ttk.Label(self.mainframe, text="Ready")
        self.status_label.grid(column=0, row=2, columnspan=2, sticky="ns", padx=5, pady=5)
    
    def _on_load_clicked(self):
        """Internal handler for load button click"""
        if self.on_load_file:
            self.on_load_file()
    
    def _on_assemble_clicked(self):
        """Internal handler for assemble button click"""
        if self.on_assemble:
            self.on_assemble()
    
    def set_load_callback(self, callback):
        """Set the callback function for load button"""
        self.on_load_file = callback
    
    def set_assemble_callback(self, callback):
        """Set the callback function for assemble button"""
        self.on_assemble = callback
    
    def show_file_dialog(self):
        """Show file selection dialog and return the selected file path"""
        file_path = filedialog.askopenfilename(
            title="Select a file",
            filetypes=[("All Files", "*.*"), ("Assembly Files", "*.asm"), ("Text Files", "*.txt")]
        )
        return file_path
    
    def update_status(self, status_text):
        """Update the status label text"""
        if self.status_label:
            self.status_label.config(text=status_text)
    
    def set_button_state(self, button_name, state):
        """Enable or disable buttons (state: 'normal' or 'disabled')"""
        if button_name == "load" and self.load_button:
            self.load_button.config(state=state)
        elif button_name == "assemble" and self.run_button:
            self.run_button.config(state=state)
    
    def run(self):
        """Start the GUI main loop"""
        if self.root:
            self.root.mainloop()
    
    def destroy(self):
        """Close the application"""
        if self.root:
            self.root.destroy()