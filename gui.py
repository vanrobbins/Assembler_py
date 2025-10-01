"""
Legacy GUI file - functionality has been refactored into MVC architecture.
Use main.py to run the application instead.

Files in the new MVC structure:
- main.py: Application entry point
- model.py: Data and business logic (AssemblerModel)
- view.py: GUI components (AssemblerView)  
- controller.py: User interaction handling (AssemblerController)
"""

# Import the new MVC structure
from main import main

# For backward compatibility, you can still run this file
if __name__ == "__main__":
    print("Note: This file has been refactored into MVC architecture.")
    print("Starting application using new structure...")
    main()
