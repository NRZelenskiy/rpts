<?php

$doc = new DOMDocument();
$doc->load('/config/php/test.xml');
//echo $doc->saveXML();

$xpath = new DOMXpath($doc);
$xpath->registerNamespace('S', 'http://www.w3.org/2003/05/soap-envelope');
$xpath->registerNamespace('ns7', 'http://russianpost.org/operationhistory');
$xpath->registerNamespace('ns6', 'http://www.russianpost.org/RTM/DataExchangeESPP/Data');
$xpath->registerNamespace('ns5', 'http://www.russianpost.org/custom-duty-info/data');
$xpath->registerNamespace('ns4', 'http://schemas.xmlsoap.org/soap/envelope/');
$xpath->registerNamespace('ns3', 'http://russianpost.org/operationhistory/data');
$xpath->registerNamespace('ns2', 'http://russianpost.org/sms-info/data');
$query = '/';
//$result = $xpath->query($query);

$nodes = $xpath->query("$query");

//echo "<pre> \n";
//foreach ($nodes as $node) {
//    foreach ($node->getElementsByTagName('OperationAddress') as $a) {
//      echo $a->nodeValue, PHP_EOL;
//    }
//}


//echo "<prepre> \n";
//$nodes= $xpath->query("//ns3:historyRecord[14]/ns3:AddressParameters[1]/ns3:OperationAddress[1]/ns3:Index[1]/text()[1]");

//foreach ($nodes as $i => $node) {
//    echo $i, $node->nodeValue, PHP_EOL;
//}


echo "<prepre> \n";
$nodes= $xpath->query("//ns3:historyRecord/ns3:AddressParameters/ns3:OperationAddress/ns3:Index/text()");

foreach ($nodes as $i => $node) {
    echo $i, $node->nodeValue, PHP_EOL;
}

$nodes= $xpath->query("//ns3:historyRecord/ns3:AddressParameters/ns3:OperationAddress/ns3:Description/text()");

foreach ($nodes as $i => $node) {
    echo $i, $node->nodeValue, PHP_EOL;
}






//echo "$entry->firstChild->nodeValue;","\n";
//echo $elements->nodeValue;

//$case1 = $xpath->query('//historyRecord[14]/AddressParameters[1]/OperationAddress[1]');
//$query = 'div[not (@class="ads")]/span[1]';
//$entries = $xpath->query($query, $case1);
//foreach ($entries as $entry){
//    echo  $entry->firstChild->nodeValue;
//}

//$query = '//S:Envelope[1]/S:Body/ns3:getOperationHistoryResponse/ns3:OperationHistoryData/ns3:historyRecord/ns3:AddressParameters/ns3:OperationAddress';
//$entries = $xpath->query($query);
//foreach ($entries as $entry) 
// {
//    echo "Значение: {$entry->nodeValue}","\n";
//  }
?>

