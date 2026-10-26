"""Capa pygame: teclado → entradas de la lógica, estado → dibujo.

pygame se importa dentro de las funciones: ``import juegos.ventana`` funciona
aunque pygame no esté instalado (y los tests de lógica no lo necesitan).

Controles
---------
Snake: flechas o WASD, P pausa, R reinicia, Esc sale.
Pong:  W/S paleta izquierda, flechas ↑/↓ paleta derecha (o IA con ``--ia``),
       Espacio pausa, R reinicia, Esc sale.
"""
from __future__ import annotations

import argparse
from typing import Any

from .pong import EventoPong, Pong, ia
from .snake import Dir, Snake

# Tamaño en píxeles de cada celda de Snake: 20x15 celdas → ventana de 480x360.
CELDA = 24
# Paleta de colores RGB compartida por ambos juegos.
NEGRO, BLANCO, VERDE, VERDE_OSC, ROJO, GRIS = (15, 15, 20), (235, 235, 235), (80, 200, 120), (40, 140, 80), (230, 70, 70), (90, 90, 100)


def dibujar_snake(sup: Any, juego: Snake, fuente: Any | None = None) -> None:
    """Dibuja el tablero en ``sup`` (una pygame.Surface de ancho·CELDA × alto·CELDA)."""
    import pygame
    sup.fill(NEGRO)
    if juego.comida:
        x, y = juego.comida
        pygame.draw.rect(sup, ROJO, (x * CELDA + 3, y * CELDA + 3, CELDA - 6, CELDA - 6), border_radius=6)
    for i, (x, y) in enumerate(juego.cuerpo):
        # La cabeza (i == 0) más clara que el cuerpo para distinguir hacia dónde va.
        pygame.draw.rect(sup, VERDE if i == 0 else VERDE_OSC, (x * CELDA + 1, y * CELDA + 1, CELDA - 2, CELDA - 2))
    if fuente:
        sup.blit(fuente.render(f"Puntos: {juego.puntos}", True, BLANCO), (6, 4))
        if not juego.vivo or juego.gano:
            msg = "¡Ganaste!" if juego.gano else "Fin del juego — R para reiniciar"
            t = fuente.render(msg, True, BLANCO)
            sup.blit(t, t.get_rect(center=sup.get_rect().center))


def dibujar_pong(sup: Any, juego: Pong, fuente: Any | None = None) -> None:
    """Dibuja red, paletas, pelota y marcador. Las coordenadas de la lógica ya son
    píxeles, así que no hay conversión (a diferencia de Snake, que usa celdas)."""
    import pygame
    sup.fill(NEGRO)
    # Red central punteada.
    for y in range(0, int(juego.alto), 20):
        pygame.draw.rect(sup, GRIS, (juego.ancho / 2 - 1, y, 2, 10))
    for pal in (juego.izq, juego.der):
        pygame.draw.rect(sup, BLANCO, (pal.x, pal.y, pal.ancho, pal.alto))
    p = juego.pelota
    pygame.draw.circle(sup, BLANCO, (round(p.x), round(p.y)), round(p.radio))
    if fuente:
        marcador = fuente.render(f"{juego.marcador[0]}   {juego.marcador[1]}", True, BLANCO)
        sup.blit(marcador, marcador.get_rect(midtop=(juego.ancho / 2, 8)))
        if juego.terminado:
            t = fuente.render(f"Gana el jugador {'izquierdo' if juego.ganador == 0 else 'derecho'} — R", True, BLANCO)
            sup.blit(t, t.get_rect(center=(juego.ancho / 2, juego.alto / 2)))


# Mapeo nombre de tecla (pygame.key.name) → dirección. Usar el nombre y no el
# código numérico hace que la tabla sea legible y fácil de testear.
TECLAS_SNAKE = {"up": Dir.ARRIBA, "w": Dir.ARRIBA, "down": Dir.ABAJO, "s": Dir.ABAJO,
                "left": Dir.IZQUIERDA, "a": Dir.IZQUIERDA, "right": Dir.DERECHA, "d": Dir.DERECHA}


def correr_snake(semilla: int | None = None, paredes: bool = True, max_cuadros: int | None = None) -> int:
    """Bucle principal. ``max_cuadros`` permite cortarlo (tests de humo con driver dummy)."""
    import pygame
    pygame.init()
    juego = Snake(semilla=semilla, paredes=paredes)
    pantalla = pygame.display.set_mode((juego.ancho * CELDA, juego.alto * CELDA))
    pygame.display.set_caption("Snake")
    fuente, reloj = pygame.font.Font(None, 28), pygame.time.Clock()
    acumulado, pausa, cuadros = 0.0, False, 0
    try:
        while max_cuadros is None or cuadros < max_cuadros:
            cuadros += 1
            # 1) Entradas: cerrar, giros (se encolan en la lógica), pausa, reinicio.
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    return 0
                if e.type == pygame.KEYDOWN:
                    nombre = pygame.key.name(e.key)
                    if nombre in TECLAS_SNAKE:
                        juego.girar(TECLAS_SNAKE[nombre])
                    elif nombre == "p":
                        pausa = not pausa
                    elif nombre == "r":
                        juego = Snake(semilla=semilla, paredes=paredes)
            # 2) Lógica. Paso fijo: la lógica avanza a juego.velocidad() ticks/s sin importar los FPS de dibujo.
            acumulado += reloj.tick(60) / 1000
            while not pausa and acumulado >= 1 / juego.velocidad():
                acumulado -= 1 / juego.velocidad()
                juego.tick()
            # 3) Dibujo: siempre a ~60 FPS, aunque la lógica vaya a 8 ticks/s.
            dibujar_snake(pantalla, juego, fuente)
            pygame.display.flip()
        return 0
    finally:
        # Siempre cerrar pygame, aun ante excepciones, para no dejar la ventana colgada.
        pygame.quit()


def correr_pong(contra_ia: bool = True, semilla: int | None = None, max_cuadros: int | None = None) -> int:
    """Bucle de Pong: dt variable (acotado) y entradas continuas (teclas mantenidas).

    A diferencia de Snake, acá no hay paso fijo: la física continua acepta cualquier
    ``dt`` porque internamente se subdivide (ver ``Pong.actualizar``).
    """
    import pygame
    pygame.init()
    juego = Pong(semilla=semilla)
    pantalla = pygame.display.set_mode((int(juego.ancho), int(juego.alto)))
    pygame.display.set_caption("Pong")
    fuente, reloj = pygame.font.Font(None, 40), pygame.time.Clock()
    pausa, cuadros = False, 0
    try:
        while max_cuadros is None or cuadros < max_cuadros:
            cuadros += 1
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    return 0
                if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                    pausa = not pausa
                if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                    juego = Pong(semilla=semilla)
            # dt acotado a 50 ms: si la ventana se arrastra o se congela, no "salta" la física.
            dt = min(reloj.tick(60) / 1000, 0.05)
            # Teclas mantenidas (no eventos): restar dos booleanos da -1, 0 o 1.
            k = pygame.key.get_pressed()
            izq = k[pygame.K_s] - k[pygame.K_w]
            der = ia(juego.der, juego.pelota) if contra_ia else k[pygame.K_DOWN] - k[pygame.K_UP]
            if not pausa:
                juego.actualizar(dt, izq, der)
            dibujar_pong(pantalla, juego, fuente)
            pygame.display.flip()
        return 0
    finally:
        # Siempre cerrar pygame, aun ante excepciones, para no dejar la ventana colgada.
        pygame.quit()


def main(argv: list[str] | None = None) -> int:
    """CLI: ``snake [--sin-paredes]`` o ``pong [--dos-jugadores]``. Devuelve el código de salida.

    Si pygame no está instalado avisa cómo instalarlo y devuelve 2, en vez de
    reventar con un ImportError poco claro.
    """
    ap = argparse.ArgumentParser(prog="juegos", description="Snake y Pong")
    sub = ap.add_subparsers(dest="juego", required=True)
    s = sub.add_parser("snake")
    s.add_argument("--sin-paredes", action="store_true", help="el tablero da la vuelta")
    s.add_argument("--semilla", type=int)
    p = sub.add_parser("pong")
    p.add_argument("--dos-jugadores", action="store_true", help="la paleta derecha la controla otra persona")
    p.add_argument("--semilla", type=int)
    a = ap.parse_args(argv)
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("instalá pygame: pip install -e '.[juego]'")
        return 2
    if a.juego == "snake":
        return correr_snake(a.semilla, not a.sin_paredes)
    return correr_pong(not a.dos_jugadores, a.semilla)


__all__ = ["main", "correr_snake", "correr_pong", "dibujar_snake", "dibujar_pong", "EventoPong"]
