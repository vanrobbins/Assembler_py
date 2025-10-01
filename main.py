"""
Main entry point for the Assembler application.
This file creates and starts the MVC application.
"""

from controller import AssemblerController


def main():
    """Main function to start the application"""
    try:
        # Create the controller (which creates model and view)
        app_controller = AssemblerController()
        
        # Start the application
        app_controller.run()
        
    except Exception as e:
        print(f"Error starting application: {e}")


if __name__ == "__main__":
    main()