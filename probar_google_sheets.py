from utils.google_sheets import probar_conexion


try:
    resultado = probar_conexion()

    print("\nCONEXIÓN CORRECTA\n")
    print(resultado)

except Exception as error:
    print("\nERROR DE CONEXIÓN\n")
    print(type(error).__name__)
    print(error)
    