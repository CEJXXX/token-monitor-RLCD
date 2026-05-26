idf_component_register(
    SRCS
    "display_bsp.cpp"
    INCLUDE_DIRS
    "./"
    # display_bsp.h is a public header that includes <driver/gpio.h>,
    # <driver/spi_master.h> and esp_lcd_*.h, so these must be public
    # (REQUIRES) to propagate include paths to consumers like main.
    # IDF 5.5 split the legacy `driver` umbrella into esp_driver_*.
    REQUIRES
    esp_driver_gpio
    esp_driver_spi
    esp_lcd
    PRIV_REQUIRES
    esp_timer)
