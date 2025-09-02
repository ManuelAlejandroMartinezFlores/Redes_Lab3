from router import *

def get_user_config():
    """Get configuration from user input."""
    print("=== Configuración del Router ===")
    
    # Basic configuration
    node_id = input("ID del router (ej: A): ").strip()
    neighbors_input = input("Vecinos (separados por coma, ej: B,C): ").strip()
    neighbors = [n.strip() for n in neighbors_input.split(',')] if neighbors_input else []
    
    # Algorithm selection
    print("\nSelección de algoritmo de enrutamiento:")
    print("1. flooding")
    print("2. link_state")
    algorithm_choice = input("Elija algoritmo (1/2 o nombre): ").strip().lower()
    
    if algorithm_choice in ['1', 'flooding']:
        algorithm = 'flooding'
    elif algorithm_choice in ['2', 'link_state']:
        algorithm = 'link_state'
    else:
        print("Usando algoritmo por defecto: flooding")
        algorithm = 'flooding'
    
    return node_id, neighbors, algorithm

if __name__ == "__main__":
    # Configuración de Redis
    REDIS_CONFIG = {
        'host': 'lab3.redesuvg.cloud',
        'port': 6379,
        'password': 'UVGRedis2025'
    }
    
    # Obtener configuración del usuario
    ROUTER_ID, NEIGHBORS, ALGORITHM = get_user_config()
    
    # Crear instancia del router
    router = RouterNode(ROUTER_ID, NEIGHBORS, REDIS_CONFIG, ALGORITHM)
    config = {
        'user_id': ROUTER_ID,
        'neighbors': NEIGHBORS,
        'algorithm': ALGORITHM
    }
    
    print(f"\n=== Router {config['user_id']} Iniciado ===")
    print(f"Conectado a Redis: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
    print(f"Vecinos: {config['neighbors']}")
    print(f"Algoritmo de enrutamiento: {config['algorithm']}")
    
    # Comandos comunes
    common_commands = [
        "'info' - Mostrar información de enrutamiento",
        "'send <objetivo> <mensaje>' - Enviar mensaje",
        "'hello <objetivo>' - Enviar hello",
        "'quit' - Salir"
    ]
    
    # Comandos específicos por algoritmo
    algorithm_specific_commands = []
    if config['algorithm'] == 'link_state':
        algorithm_specific_commands = [
            "'flood' - Flood LSA a vecinos",
            "'route <objetivo>' - Mostrar ruta a objetivo"
        ]
    
    # Mostrar todos los comandos
    print("\nComandos disponibles:")
    for cmd in common_commands + algorithm_specific_commands:
        print(f"  {cmd}")
    
    try:
        while True:
            command = input("\nComando: ").strip()
            
            if command == 'info':
                router.print_routing_info()
                
            elif command == 'flood' and config['algorithm'] == 'link_state':
                router.flood_lsa()
                print("LSA enviado a vecinos")
                    
            elif command.startswith('send '):
                parts = command.split(' ', 2)
                if len(parts) >= 3:
                    target = parts[1]
                    message = parts[2]
                    success = router.send_data(target, message)
                    if success:
                        print(f"Mensaje enviado a {target}")
                    else:
                        print(f"Error: No se pudo enviar mensaje a {target}")
                else:
                    print("Uso: send <objetivo> <mensaje>")
                    
            elif command.startswith('hello '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.send_hello(target)
                    print(f"Ping enviado a {target}")
                else:
                    print("Uso: hello <objetivo>")
                    
            elif command.startswith('route ') and config['algorithm'] == 'link_state':
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.request_route(target)
                else:
                    print("Uso: route <objetivo>")
                    
            elif command == 'quit':
                break
                
            else:
                print("Comando desconocido. Comandos disponibles:")
                for cmd in common_commands + algorithm_specific_commands:
                    print(f"  {cmd}")
                
    except KeyboardInterrupt:
        print("\nApagando router...")
    finally:
        router.stop()
