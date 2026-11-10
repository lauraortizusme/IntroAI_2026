# Asistente conversacional para descubrir videojuegos

**Proyecto final Inteligencia Artificial 
Opción B: agente con herramientas**

**Integrantes:** 

## 1. Descripción del proyecto

Elegir un videojuego puede ser difícil cuando una persona tiene una idea
general de lo que quiere, pero no conoce los géneros o etiquetas que
debería buscar. Por ejemplo: «quiero algo relajante para jugar con mis
amigos y que funcione en Mac».

Este proyecto propone un agente conversacional que interpreta
solicitudes en lenguaje natural y consulta un catálogo de videojuegos de
Steam. Según la tarea, el modelo de lenguaje selecciona herramientas
para filtrar juegos, buscar por similitud semántica, consultar la ficha
de un título o calcular precios. La aplicación ejecuta las herramientas
y devuelve sus resultados al modelo, que formula una recomendación
basada en los datos consultados.

El prototipo está dirigido a jugadores que necesitan ayuda para traducir
sus preferencias a criterios de búsqueda.

## 2. Problema y solución

Las tiendas de videojuegos suelen organizar sus filtros mediante
categorías y etiquetas predeterminadas. Sin embargo, los jugadores
pueden describir lo que buscan mediante sensaciones, situaciones o
preferencias expresadas libremente. Convertir esas descripciones en
filtros concretos requiere conocer las categorías de la tienda y puede
hacer que la búsqueda resulte lenta o frustrante.

La solución consiste en un agente que interpreta la solicitud, decide
qué herramientas utilizar y combina búsquedas semánticas con filtros y
operaciones sobre los datos. Para evitar recomendaciones sin respaldo,
el agente solo debe recomendar títulos devueltos por las herramientas y
presentar sus precios y sistemas operativos a partir del catálogo.

## 3. Alcance

### Funcionalidades incluidas

  -----------------------------------------------------------------------
  Tarea                   Ejemplo                 Herramienta
  ----------------------- ----------------------- -----------------------
  Búsqueda con criterios  «Un shooter cooperativo `buscar_juegos`
  concretos               por menos de 10 USD»    

  Búsqueda por            «Algo relajante,        `buscar_similares`
  descripción libre       parecido a un juego de  
                          granja»                 

  Consulta de un título   «¿Cuánto cuesta y en    `detalle_juego`
                          qué sistemas funciona   
                          \[juego\]?»             

  Cálculo de precios      «¿Cuánto cuestan juntos `calcular_total`
                          estos tres juegos?»     

  Solicitud combinada     «Busca juegos           Varias herramientas
                          relajantes por menos de 
                          15 USD en Mac y calcula 
                          cuánto cuestan los dos  
                          primeros»               
  -----------------------------------------------------------------------

En este proyecto, **plataforma** se refiere a sistema operativo de PC:
Windows, macOS o Linux. El catálogo corresponde a Steam; no incluye
consolas ni otras tiendas.

### Fuera del alcance

-   Comprar juegos, generar enlaces de pago o integrarse con la tienda
    de Steam.
-   Consultar precios o disponibilidad en tiempo real.
-   Analizar reseñas completas u opiniones de usuarios.
-   Personalizar recomendaciones mediante el historial o la cuenta del
    jugador.
-   Consultar catálogos de consolas, dispositivos móviles u otras
    tiendas.
-   Implementar varios agentes o desplegar el sistema como servicio de
    producción.

## 4. ¿Por qué un agente con herramientas?

Se eligió la **opción B: agente con herramientas**, en lugar de un
sistema RAG, porque las solicitudes combinan dos tipos de información:

-   **Preferencias semánticas:** por ejemplo, «relajante», «aventura
    tranquila» o «para jugar con amigos».
-   **Condiciones verificables:** por ejemplo, un precio máximo o la
    compatibilidad con macOS.

El catálogo es una tabla estructurada con información de los juegos. Por
ello, los filtros exactos, las consultas de fichas y los cálculos se
resuelven directamente sobre los datos. La búsqueda semántica
complementa estas operaciones cuando la persona describe lo que quiere
sin utilizar las etiquetas de Steam.

El elemento central es la decisión del modelo: seleccionar una
herramienta, proporcionar sus argumentos, interpretar el resultado y
decidir si necesita otra llamada. `buscar_similares` utiliza embeddings,
pero es una herramienta dentro del agente; no convierte el sistema en un
RAG.

## 5. Datos

**Fuente principal:** [Steam Games Dataset ---
FronkonGames](https://huggingface.co/datasets/FronkonGames/steam-games-dataset),
publicado en Hugging Face. La ficha del conjunto de datos indica que
contiene información de juegos de Steam y que se distribuye bajo
licencia CC-BY-4.0. Se conservará la atribución correspondiente a la
fuente.

**Selección del catálogo:** se utilizará un recorte de aproximadamente
1.000 juegos con descripción disponible y en inglés, priorizando los
títulos con mayor número de reseñas. El criterio definitivo de
selección, el tamaño exacto y la fecha de descarga se documentarán
cuando se prepare el archivo final.

**Campos previstos:** nombre, descripción, géneros, etiquetas, precio,
sistemas operativos, reseñas positivas y negativas y fecha de
lanzamiento. Los nombres definitivos de las columnas se confirmarán al
procesar el archivo original.

**Preparación de datos:**

1.  Descargar el conjunto de datos y documentar su versión o fecha de
    consulta.
2.  Seleccionar los registros según el criterio definido.
3.  Normalizar los tipos de datos, especialmente el precio y las listas
    de géneros y etiquetas.
4.  Eliminar duplicados y registros sin descripción.
5.  Guardar el catálogo procesado.
6.  Generar una sola vez los embeddings de las descripciones y
    almacenarlos para reutilizarlos.

El catálogo es una captura fija: los precios y demás datos pueden no
coincidir con los disponibles actualmente en Steam.

## 6. Arquitectura

El sistema se organiza en dos procesos: **preparación de datos**, que se
realiza antes de ejecutar el agente, y **consulta**, que se repite cada
vez que el usuario envía una solicitud.

``` mermaid
flowchart TB
    subgraph PREP["Preparación de datos (previa)"]
        A["Dataset de Steam"] --> B["Limpieza y selección"]
        B --> C["Catálogo procesado (CSV)"]
        B --> D["Embeddings de descripciones"]
    end

    subgraph RUN["Ejecución del agente"]
        U["Usuario"] <--> UI["Interfaz Gradio"]
        UI --> APP["Aplicación: ciclo del agente"]
        APP <--> LLM["LLM · NVIDIA NIM<br/>Decide qué herramienta utilizar"]
        APP --> T["Herramientas Python"]
        T --> CSV["Catálogo CSV"]
        T --> V["Índice de embeddings"]
        CSV --> T
        V --> T
        T --> APP
        APP --> UI
    end

    C -.-> CSV
    D -.-> V
```

### Ciclo de ejecución

1.  El usuario envía una solicitud desde la interfaz.
2.  La aplicación envía al modelo el mensaje, el historial pertinente y
    las descripciones de las herramientas disponibles.
3.  El modelo decide si puede responder o si necesita solicitar una
    herramienta.
4.  Cuando solicita una herramienta, la aplicación valida sus
    argumentos, la ejecuta y registra el nombre, los argumentos y el
    resultado.
5.  La aplicación devuelve el resultado al modelo, que puede responder o
    solicitar otra herramienta.
6.  El ciclo termina cuando el modelo produce una respuesta final o se
    alcanza el límite de llamadas.
7.  La interfaz muestra la respuesta y la traza de ejecución.

### Límite de llamadas y errores

Se establece un máximo de **cinco llamadas a herramientas por solicitud
del usuario**. Si se alcanza, la aplicación realiza una última consulta
al modelo sin habilitar nuevas herramientas, para que responda con la
información reunida y advierta que la búsqueda quedó incompleta.

Las herramientas validan sus argumentos y devuelven resultados
estructurados. Casos como un juego inexistente, argumentos inválidos o
una búsqueda sin coincidencias deben comunicarse al modelo como
resultados controlados, en lugar de interrumpir el ciclo con una
excepción no gestionada.

## 7. Herramientas

Las cuatro herramientas se implementan como funciones Python
independientes y se describen al modelo mediante esquemas de function
calling.

  --------------------------------------------------------------------------
  Herramienta          Propósito         Argumentos        Resultado
                                         principales       
  -------------------- ----------------- ----------------- -----------------
  `buscar_juegos`      Aplicar filtros   `genero`, `tags`, Juegos que
                       exactos al        `precio_max`,     cumplen los
                       catálogo          `plataforma`,     criterios, con
                                         `limite`          sus datos
                                                           relevantes

  `buscar_similares`   Encontrar         `descripcion`,    Juegos más
                       descripciones     `k`, filtros      similares y
                       cercanas          opcionales        puntajes de
                       semánticamente a                    similitud
                       una solicitud                       

  `detalle_juego`      Consultar la      `nombre`          Datos del juego o
                       ficha de un                         aviso de que no
                       título                              se encontró

  `calcular_total`     Calcular el costo `nombres`         Precios
                       de varios títulos                   individuales,
                                                           suma y promedio,
                                                           o aviso de
                                                           títulos no
                                                           encontrados
  --------------------------------------------------------------------------

`buscar_juegos` se encarga de las condiciones exactas;
`buscar_similares` identifica cercanía de significado. Cuando una
solicitud combina ambas, el diseño debe asegurar que los filtros
obligatorios ---como precio máximo y sistema operativo--- se apliquen y
verifiquen, aunque también se utilice similitud semántica.

`calcular_total` recibe nombres de juegos y consulta sus precios en el
catálogo. No recibe expresiones de código ni precios inventados por el
modelo.

## 8. Tecnologías

  -----------------------------------------------------------------------
  Tecnología                          Uso
  ----------------------------------- -----------------------------------
  Python                              Implementación del agente y las
                                      herramientas

  NVIDIA NIM                          Modelo de lenguaje con function
                                      calling: \[modelo por confirmar\]

  NVIDIA NIM --- embeddings           Representación vectorial de
                                      descripciones: \[modelo por
                                      confirmar\]

  Cliente `openai`                    Comunicación con la API compatible
                                      de NVIDIA NIM

  pandas                              Lectura, limpieza y filtrado del
                                      catálogo

  Gradio                              Interfaz conversacional y panel de
                                      trazabilidad

  python-dotenv                       Lectura de variables de entorno

  Steam Games Dataset                 Fuente del catálogo
  -----------------------------------------------------------------------

## 9. Interfaz

Se propone una interfaz web en Gradio, ejecutable localmente o en Google
Colab. Tendrá dos áreas principales:

-   **Conversación:** historial de mensajes, campo para escribir
    solicitudes, botón de envío y ejemplos de consultas.
-   **Traza de herramientas:** lista de llamadas realizadas, argumentos
    enviados, resultados devueltos y contador de llamadas respecto al
    máximo permitido.

La respuesta puede presentar los juegos recomendados en tarjetas o una
lista con nombre, precio, sistemas operativos y géneros. La traza debe
permitir consultar los argumentos y resultados de cada llamada, sin
ocultar los casos en los que no hubo resultados o se produjo un error.

## 10. Instalación y ejecución

1.  Clonar el repositorio e instalar las dependencias:

    ``` bash
    pip install -r requirements.txt
    ```

2.  Crear un archivo `.env` a partir de `.env.example` y configurar la
    clave:

    ``` env
    NVIDIA_API_KEY=tu_clave_aqui
    ```

    En Google Colab se utilizarán los secretos del entorno. **No se
    deben incluir claves reales en el código, los notebooks ni el
    repositorio.**

3.  Obtener los datos siguiendo las instrucciones de `data/` o utilizar
    el CSV procesado incluido en el repositorio.

4.  Ejecutar la aplicación:

    ``` bash
    python src/app.py
    ```

    \[Ajustar este comando cuando se confirme la estructura y el punto
    de entrada definitivos.\]

## 11. Pruebas y resultados

La evaluación será manual. En cada caso se comparará la respuesta con el
catálogo original y con los resultados de las herramientas. Se revisará
si la herramienta seleccionada fue adecuada, si sus argumentos
representan la solicitud y si la respuesta final coincide con los datos
devueltos.

  -----------------------------------------------------------------------
  \#                Categoría         Solicitud         Resultado
                                                        esperado
  ----------------- ----------------- ----------------- -----------------
  1                 Habitual: filtros «Un shooter       Los resultados
                                      cooperativo por   cumplen los
                                      menos de 10 USD»  filtros
                                                        disponibles en el
                                                        catálogo.

  2                 Habitual:         «Quiero algo para Las
                    semántica         relajarme»        recomendaciones
                                                        son coherentes
                                                        con la
                                                        descripción y
                                                        aparecen en los
                                                        resultados de la
                                                        herramienta.

  3                 Habitual:         «Recomiéndame     Se identifican
                    combinada         tres juegos de    los juegos y el
                                      granja y dime     total coincide
                                      cuánto cuestan    con la suma de
                                      juntos»           sus precios en el
                                                        catálogo.

  4                 Consulta que      «¿En qué sistemas La ficha coincide
                    requiere          operativos        con los datos del
                    herramienta       funciona \[juego  catálogo.
                                      del catálogo\] y  
                                      cuánto cuesta?»   

  5                 Caso límite       «¿Cuánto cuesta   El agente
                                      \[título que no   reconoce que no
                                      está en el        encuentra el
                                      catálogo\]?»      título y no
                                                        inventa
                                                        información.

  6                 Prueba adicional: Solicitud que     El agente
                    límite de         provoque más de   responde con lo
                    llamadas          cinco llamadas    reunido e informa
                                                        que la búsqueda
                                                        quedó incompleta.
  -----------------------------------------------------------------------

Para cada caso se registrarán la respuesta obtenida, las herramientas
llamadas, sus argumentos y resultados, y una valoración (**correcto,
parcial o incorrecto**) con su justificación. La traza completa se
incluirá al menos en dos casos.

### Análisis de resultados

**Error o limitación observada:** \[documentar un error real de las
pruebas, su efecto y una posible mejora\].

Si los casos funcionan correctamente, se analizará el caso más difícil y
se explicará qué limitación podría aparecer en otro escenario.

## 12. Limitaciones y mejoras posibles

  -----------------------------------------------------------------------
  Limitación                          Mejora posible
  ----------------------------------- -----------------------------------
  Las descripciones están en inglés y Utilizar embeddings multilingües o
  las solicitudes pueden estar en     traducir la consulta antes de
  español.                            buscar.

  Las etiquetas de Steam no siempre   Combinar filtros con búsqueda
  representan las preferencias        semántica y normalizar etiquetas.
  expresadas por el usuario.          

  El modelo puede seleccionar una     Mejorar las descripciones de las
  herramienta poco adecuada.          funciones e incorporar ejemplos al
                                      prompt.

  El catálogo contiene un número      Ampliar el conjunto de datos o
  limitado de juegos.                 utilizar una fuente actualizable.

  Los datos corresponden a una        Actualizar periódicamente el
  captura fija.                       catálogo.
  -----------------------------------------------------------------------

## 13. Fuentes

-   FronkonGames. *Steam Games Dataset*. Hugging Face.
    https://huggingface.co/datasets/FronkonGames/steam-games-dataset.
    Licencia indicada en la ficha: CC-BY-4.0.
-   Material de SI3003 Inteligencia Artificial: [notebooks de agentes
    ---
    Lecture11](https://github.com/EAFIT-IA/si3003-artificial-intelligence/tree/main/notebooks/Lecture11)
    y [notebooks de RAG ---
    lecture10](https://github.com/EAFIT-IA/si3003-artificial-intelligence/tree/main/notebooks/lecture10).
