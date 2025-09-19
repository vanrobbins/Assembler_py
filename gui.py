from tkinter import *
from tkinter import ttk
from tkinter import filedialog

# Variable to store the selected file path
target_file = ""
#Function that opens file explorer to select input file
def open_file_dialog():
	global target_file
	file_path = filedialog.askopenfilename(
		title="Select a file",
		filetypes=[("All Files", "*.*")]
	)
	if file_path:
		status.config(text=f"Loaded: {file_path}")
		target_file = file_path
	elif target_file:
		status.config(text=f"Loaded: {file_path}")
	else:
		status.config(text=f"No File Selected")
#Empty function that acts as assemble runner
def run_assemble():
    assemble(target_file)
#TODO connect to main somehow so actual logic is not in this function just calls
def assemble(source):
	if source.strip():
		status.config(text=f"running");
	else:
		status.config(text=f"No file selected to run")
	
root = Tk()
root.title("Assembler in Python")
root.geometry("600x400")
# Configure the root window's grid so the frame expands
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
# Create and place the ttk.Frame to fill the root window
mainframe = ttk.Frame(root, padding="10")
mainframe.grid(column=0, row=0, sticky="nsew")

# Configure the mainframe's internal grid so buttons expand
mainframe.columnconfigure(0, weight=1)
mainframe.columnconfigure(1, weight=1)
mainframe.rowconfigure(0, weight=1)
mainframe.rowconfigure(1, weight=1)
mainframe.rowconfigure(2, weight=1)
# Create and place four buttons in the mainframe's grid
title = ttk.Label(mainframe, text="Assembler in Python")
title.grid(column=0, row=0,columnspan=2, sticky="ns", padx=5, pady=5)


load = ttk.Button(mainframe, text="Load File",cursor="hand2", command=open_file_dialog)
load.grid(column=0, row=1, sticky="nsew", padx=5, pady=5)

run = ttk.Button(mainframe, text="Assemble",cursor="hand2", command=run_assemble)
run.grid(column=1, row=1, sticky="nsew", padx=5, pady=5)

status = ttk.Label(mainframe, text="Status")
status.grid(column=0, row=2,columnspan=2, sticky="ns", padx=5, pady=5)
