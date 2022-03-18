
// service name, e.g. 'sos', 'case', 'customer', 'machineid', 'hostname', etc...
var SauceryService;
// service value, e.g. sosreport name for 'sos', case number for 'case', etc...
var SauceryServiceValue;
// service path, i.e. any path after key; used mostly for 'sos', e.g. /files/...
var SauceryServicePath;

if (window.location.pathname.endsWith('.html')) {
    SauceryService = window.location.pathname.split('/').slice(-1)[0].split('.')[0];
    let value = new URLSearchParams(window.location.search).get(SauceryService).split('/');
    SauceryServiceValue = value[0];
    SauceryServicePath = value.slice(1).join('/');
} else {
    let path = window.location.pathname.split('/');
    SauceryService = path[1];
    SauceryServiceValue = path[2];
    SauceryServicePath = path.slice(3).join('/');
}

var SauceryReport = [];
var SauceryReportLoaded = $.getJSON('/sauceryreport.json', data => SauceryReport = data);
function SauceryReportReady(callback) {
    $.when(SauceryReportLoaded).done(callback);
}

// Set link to main index
$(() => $('.mainindex').css('text-align', 'center').append($('<a>').attr('href', '/').text('Return to main index')));

// keys are fields, values are functions to generate hrefs
var SauceryAnchorHrefFunctions = {
    'case': ((v, e) => '/case/' + v),
    'customerid': ((v, e) => '/customer/' + v),
    'customername': ((v, e) => '/customer/' + e.customerid),
    'hostname': ((v, e) => '/hostname/' + v),
    'machineid': ((v, e) => '/machineid/' + v),
    'name': ((v, e) => '/sos/' + v),
    'sosreport': ((v, e) => '/sos/' + v),
}
var SauceryAnchorTextFunctions = {
    'datetime': ((v, e) => DateToYMD(new Date(v))),
}
// entry fields that should be updated on page load
var SauceryAnchorFields = Object.keys(SauceryAnchorHrefFunctions).concat(Object.keys(SauceryAnchorTextFunctions));

// keys are fields, values are header text
var SauceryTableHeaders = {
    'customername': 'Customer',
    'case': 'Case',
    'hostname': 'Hostname',
    'machineid': 'Machine ID',
    'datetime': 'Date',
    'name': 'SOS',
}
// table column fields, in order they should be displayed
var SauceryTableFields = Object.keys(SauceryTableHeaders);

// params is an object with optional fields:
//   filter: a function passed to entries.filter(); this overrides field/value filtering
//   field: a field of each entry to filter on, default SauceryService
//   value: the value to match each entry field with, default SauceryServiceValue
//   anchorFields: Array of fields to update DOM elements, default SauceryAnchorFields
//   anchorHrefFunctions: Object in same format as default, SauceryAnchorHrefFunctions
//   anchorTextFunctions: Object in same format as default, SauceryAnchorTextFunctions
//   tableFields: Array of fields to include in table, default SauceryTableFields
//   tableHeaders: Object in same format as default, SauceryTableHeaders
function SelectSOSEntries(params={}) {
    if (params.filter)
        filterfunction = params.filter;
    else
        filterfunction = (entry => entry[params.field || SauceryService] == (params.value || SauceryServiceValue));

    anchorFields = params.anchorFields || SauceryAnchorFields;
    anchorHrefFunctions = params.anchorHrefFunctions || SauceryAnchorHrefFunctions;
    anchorTextFunctions = params.anchorTextFunctions || SauceryAnchorTextFunctions;
    tableFields = params.tableFields || SauceryTableFields;
    tableHeaders = params.tableHeaders || SauceryTableHeaders;

    SauceryReportReady(function () {
        let SOSEntries = SauceryReport.filter(filterfunction);

        anchorFields.forEach(function (field) {
            let entries = SOSEntries.filter(entry => entry[field])
                .reduce(function (list, entry) {
                    if (!list.map(entry => entry[field]).includes(entry[field]))
                        list.push(entry);
                    return list;
                }, [])
                .sort((a, b) => a[field].localeCompare(b[field]));

            let anchors = entries.map(function (entry) {
                return SauceryAnchor(entry, field, anchorTextFunctions[field], anchorHrefFunctions[field]);
            });

            $('.' + field).append(JoinAnchors(anchors));
        });

        SauceryTable('.SauceryTable', SOSEntries, tableFields, tableHeaders, anchorTextFunctions, anchorHrefFunctions);

        if (SauceryService == 'sos') {
            SauceryHotSOS('.hotsos');
            SauceryTree('.SauceryTree');
        }
    });
}

function SauceryAnchor(entry, field, textfunction, hreffunction) {
    if (textfunction === undefined)
        textfunction = SauceryAnchorTextFunctions[field];
    if (hreffunction === undefined)
        hreffunction = SauceryAnchorHrefFunctions[field];

    let value = entry[field];
    let text = textfunction ? textfunction(value, entry) : value;
    let href = hreffunction ? hreffunction(value, entry) : undefined;
    let a = $('<a>').text(text);

    if (href)
        a.attr('href', href);

    return a;
}

function SauceryTable(elements,
                      entries,
                      fields=SauceryTableFields,
                      headers=SauceryTableHeaders,
                      textfunctions=SauceryAnchorTextFunctions,
                      hreffunctions=SauceryAnchorHrefFunctions) {
    let table = $('<table>');
    let thead = $('<thead>').appendTo(table);
    let tbody = $('<tbody>').appendTo(table);

    let tr = $('<tr>').appendTo(thead);
    fields.forEach(function (field) {
        let header = headers[field] || field;
        $('<th>').text(header).appendTo(tr);
    });

    entries.forEach(function (entry) {
        let tr = $('<tr>').appendTo(tbody);
        fields.forEach(function (field) {
            let anchor = SauceryAnchor(entry, field, textfunctions[field], hreffunctions[field]);
            $('<td>').append(anchor).appendTo(tr);
        });
    });

    table.appendTo(elements).DataTable({
        'pageLength': 25,
        'order': [[ 4, 'desc' ], [ 2, 'desc' ]],
    });
}

function SauceryHotSOS(elements) {
    $('<a>').attr('href', '/sos/' + SauceryServiceValue + '/hotsos.yaml').text('HotSOS')
        .appendTo(elements);
}

function SauceryTree(elements) {
    let sospath = SauceryServicePath.split('/').filter(p => p).reverse();

    if (sospath.length == 0) {
        $('<a>').attr('href', 'files').text('files').appendTo(elements);
        return;
    }

    let href = '';
    let anchors = sospath.map(function (name) {
        let a = $('<a>').attr('href', href).text(name);
        href = href + '../';
        return a;
    }).reverse();
    $('<p>').append(JoinAnchors(anchors, '/')).appendTo(elements);

    let jstree_data = function (obj, callback) {
        let path = this.get_path(obj, '/') || '';
        $.getJSON(path, {'format': 'json'}, function (data) {
            callback(data.map(function (child) {
                let href = (path ? path + '/' : '') + encodeURIComponent(child.name);
                return {
                    'text': child.name,
                    'icon': false,
                    'a_attr': {
                        'href': href,
                    },
                    'href': href,
                    'children': child.type == 'directory',
                }
            }));
        });
    };

    $('<p>').jstree({'core': {'data': jstree_data}})
        .on('select_node.jstree', (evt, data) => window.location = data.node.original.href)
        .appendTo(elements);
}

function DateToYMD(date) {
    return (String(date.getUTCFullYear()).padStart(4, '0') + '-' +
            String(date.getUTCMonth()+1).padStart(2, '0') + '-' +
            String(date.getUTCDate()).padStart(2, '0'));
}

function JoinAnchors(anchors, separatortext=', ') {
    let list = anchors.flatMap(a => [a, $('<a>').text(separatortext)]);
    list.pop();
    return list;
}
