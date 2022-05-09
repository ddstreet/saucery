
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

var SauceryMenu = [];
var SauceryMenuLoaded = $.getJSON('/menu.json', data => SauceryMenu = data);
function SauceryMenuReady(callback) {
    $.when(SauceryMenuLoaded).done(callback);
}

// Set link to main index
$(() => $('.mainindex').css('text-align', 'center').append($('<a>').attr('href', '/').text('Return to main index')));

// keys are fields, values are functions to generate hrefs
var SauceryAnchorHrefFunctions = {
    'case': ((v, e) => '/case/' + v),
    'customer': ((v, e) => '/customer/' + v),
    'hostname': ((v, e) => '/hostname/' + v),
    'machineid': ((v, e) => '/machineid/' + v),
    'name': ((v, e) => '/sos/' + v),
    'sosreport': ((v, e) => '/sos/' + v),
}
var SauceryAnchorTextFunctions = {
    'datetime': ((v, e) => DateToYMD(new Date(v))),
    'conclusions_critical': ((v, e) => v.toString()),
    'conclusions_error': ((v, e) => v.toString()),
    'conclusions_warning': ((v, e) => v.toString()),
    'conclusions_info': ((v, e) => v.toString()),
    'conclusions_debug': ((v, e) => v.toString()),
}
// entry fields that should be updated on page load
var SauceryAnchorFields = [
    'case',
    'customer',
    'hostname',
    'machineid',
    'name',
    'sosreport',
]

// keys are fields, values are header text
var SauceryTableHeaders = {
    'customer': 'Customer',
    'case': 'Case',
    'hostname': 'Hostname',
    'machineid': 'Machine ID',
    'datetime': 'Date',
    'name': 'SOS',
    'conclusions_critical': 'Criticals',
    'conclusions_error': 'Errors',
    'conclusions_warning': 'Warnings',
    'conclusions_info': 'Infos',
    'conclusions_debug': 'Debugs',
}
// table column fields, in order they should be displayed
var SauceryTableFields = [
    'customer',
    'case',
    'hostname',
    'machineid',
    'datetime',
    'name',
    'conclusions_critical',
    'conclusions_error',
    'conclusions_warning',
]

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
        filterfunction = (entry => encodeURIComponent(entry[params.field || SauceryService]) == (params.value || SauceryServiceValue));

    anchorFields = params.anchorFields || SauceryAnchorFields;
    anchorHrefFunctions = params.anchorHrefFunctions || SauceryAnchorHrefFunctions;
    anchorTextFunctions = params.anchorTextFunctions || SauceryAnchorTextFunctions;
    tableFields = params.tableFields || SauceryTableFields;
    tableHeaders = params.tableHeaders || SauceryTableHeaders;

    SauceryMenuReady(function () {
        let SOSEntries = SauceryMenu.filter(filterfunction);

        anchorFields.forEach(function (field) {
            let entries = SOSEntries.filter(entry => entry[field])
                .reduce(function (list, entry) {
                    if (!list.map(entry => entry[field]).includes(entry[field]))
                        list.push(entry);
                    return list;
                }, [])
                .sort((a, b) => a[field].toString().localeCompare(b[field].toString()));

            let anchors = entries.map(function (entry) {
                return SauceryAnchor(entry, field, anchorTextFunctions[field], anchorHrefFunctions[field]);
            });

            $('.' + field).append(JoinAnchors(anchors));
        });

        SauceryTable('.SauceryTable', SOSEntries, tableFields, tableHeaders, anchorTextFunctions, anchorHrefFunctions);
        SauceryTree('.SauceryTree');
    });
}

function SauceryAnchor(entry, field, textfunction, hreffunction) {
    if (textfunction === undefined)
        textfunction = SauceryAnchorTextFunctions[field];
    if (hreffunction === undefined)
        hreffunction = SauceryAnchorHrefFunctions[field];

    let value = entry[field];
    let text = textfunction ? textfunction(value, entry) : value;
    let href = hreffunction ? hreffunction(encodeURIComponent(value), entry) : undefined;
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
