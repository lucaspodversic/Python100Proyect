"""Snake y Pong.

La lógica (``snake``, ``pong``) es Python puro y determinista: no importa
pygame, no lee el reloj ni el teclado. Recibe "entradas" (dirección, tecla) y
un ``dt`` y devuelve eventos. La capa ``ventana`` traduce teclado → entradas y
estado → píxeles. Así se testea todo sin pantalla.
"""
