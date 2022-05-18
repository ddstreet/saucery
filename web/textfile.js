
function TextFile() {
    let table = $('<table>');
    let tbody = $('<tbody>').appendTo(table);
    let newlines = ['', SauceryService, SauceryServiceValue, 'lines', SaucerySubServicePath].join('/');

    $.get(newlines, (data => GetNewlines(data, tbody)));

    return table;
}

var SauceryLineNumbers;

function GetNewlines(data, tbody) {
    SauceryLineNumbers = data.split(',');

    PopulateTextFile(tbody)
}

function PopulateTextFile(tbody) {
    let startline = Number(SauceryParams.get('start')) || 1;
    let endline = Number(SauceryParams.get('end')) || startline + 10;

    // Adjust 1-based startline to 0-based array index,
    // and adjust endline to include line content up to next line start,
    // and also adjust endline to account for slice() not including end value
    let offsets = SauceryLineNumbers.slice(startline - 1, endline + 1);
    if (offsets.length == 0)
        return;

    let range = 'bytes=' + offsets[0] + '-' + offsets.slice(-1)[0];

    $.ajax(window.location.pathname, {
        data: { format: 'raw', },
        headers: {
            'Range': range,
        },
        success: (data => UpdateTextFile(tbody, data, startline, offsets, window.location.hash)),
    });
}

function AddTextLines(after, data, startline, offsets) {
    let start = 0;
    let base = offsets[0];
    let linenumber = startline;

    offsets.slice(1).forEach(end => {
        let tr = $('<tr>').attr('id', 'LINE' + linenumber).insertAfter(after);
        end = end - base;
        let content = data.slice(start, end);
        $('<td>').addClass('linenumber').text(linenumber).appendTo(tr);
        $('<td>').addClass('linecontent').text(content).appendTo(tr);
        start = end;
        linenumber = linenumber + 1
    });
}

function UpdateTextFile(tbody, data, startline, offsets, scrollto) {
    let uptr = $('<tr>').attr('id', 'LINEUP').appendTo(tbody);
    let upbutton = $('<button>').text('^ load more lines ^')
        .click(_ => LoadLinesUp(tbody));
    $('<td>').appendTo(uptr);
    $('<td>').append(upbutton).appendTo(uptr);

    AddTextLines(uptr, data, startline, offsets);

    let downtr = $('<tr>').attr('id', 'LINEDOWN').appendTo(tbody);
    let downbutton = $('<button>').text('v load more lines v')
        .click(_ => LoadLinesDown(tbody));
    $('<td>').appendTo(downtr);
    $('<td>').append(downbutton).appendTo(downtr);

    if (String(scrollto).startsWith('#LINE') && $(scrollto).length == 1)
        $('body').animate({ scrollTop: $(scrollto).offset().top, }, 500);

    HideTextButtons(tbody);
}

function LoadLinesUp(tbody) {
    
}

function LoadLinesDown(tbody) {
    alert('loading lines down');
}

function HideTextButtons(tbody) {
    if ($('#LINE1').length == 1)
        $('#LINEUP').hide(duration=0);
    if ($('#LINE' + (SauceryLineNumbers.length - 1)).length == 1)
        $('#LINEDOWN').hide(duration=0);
}
