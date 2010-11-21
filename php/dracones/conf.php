<?php

/*!
  @defgroup conf
  Dracones module auto-configuration.
  The import of this script reads the dracones core config file and import all the 
  specific application config files found in a dict, exposed as the "dconf" global 
  variable.
*/

$dconf = array();

function runConf() {

    global $dconf;

    if (!function_exists('ms_GetVersionInt') || ms_GetVersionInt() < 50600) {
        die('Dracones-PHP is only compatible with MapServer >= 5.6');
    }
       
    $conf_filepath = 'conf.json';
    $dconf = json_decode(file_get_contents($conf_filepath, FILE_USE_INCLUDE_PATH), true); // assoc=true: array
    
    foreach ($dconf['app_conf_filepaths'] as $app_conf_filepath) {
        $app_conf = json_decode(file_get_contents($app_conf_filepath), true); // assoc=true: array
        assert(array_key_exists('app_name', $app_conf));
        $dconf[$app_conf['app_name']] = $app_conf;
    }

}

runConf();

?>
