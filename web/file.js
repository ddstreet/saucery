
// This is an array of each line offset into the file.
// The line offsets always start with 0, since line 1 is always at 0,
// and each following offset is immediately after each newline,
// and includes the offset after EOF, meaning the final entry == file size,
// and this this array's length is 1 more than the total number of lines
var SauceryLineOffsets;

function SauceryFirstLineNumber() { return 1; }
function SauceryLastLineNumber() { return SauceryLineOffsets.length - 1; }

// Line to scroll page to on first load, e.g. #LINE50
function SauceryBookmarkLineNumber() {
    if (window.location.hash.startsWith('#LINE'))
        return Number(window.location.hash.slice(5));
    return NaN;
}

// First line shown
function SauceryFirstLoadedLine() { return $('.TextFile>table>tbody').children('tr').first(); }
// Last line shown
function SauceryLastLoadedLine() { return $('.TextFile>table>tbody').children('tr').last(); }

function LineNumber(tr) { return Number(tr.attr('id').slice(4)); }

// This does initialization of the file content, if an element with class 'TextFile' exists
$(TextFile);

function TextFile() {
    let textfile = $('.TextFile');
    if (textfile.length == 0)
        return;

    let table = $('<table>').append($('<tbody>'));
    let newlines = SauceryPathEntries.slice(0, -1)
        .concat('.SAUCERY_LINES', SauceryPathEntries.at(-1)).join('/');

    let startline = 1;
    let endline = 120;
    if (SauceryBookmarkLineNumber()) {
        startline = Math.max(1, SauceryBookmarkLineNumber() - 100);
        endline = SauceryBookmarkLineNumber() + 100;
    }

    $.ajax(newlines, {
        data: {
            format: 'raw',
        },
        success: (data => {
            SauceryLineOffsets = data.split(',');
            startline = Math.min(startline, SauceryLastLineNumber() - 100);
            endline = Math.max(endline, SauceryFirstLineNumber() + 100);
            LoadRange(startline, endline).done(ScrollToLineNumber);
        }),
        error: (_ => {
            let location = window.location;
            let params = new URLSearchParams(location.search);
            params.set('format', 'raw');
            location.search = params;
        }),
    });

    textfile.append(table);
}

function ScrollToLineNumber() {
    if (SauceryBookmarkLineNumber()) {
        let scrollToLine = $('#LINE'+SauceryBookmarkLineNumber());
        if (scrollToLine.length) {
            $('body').animate({ scrollTop: scrollToLine.offset().top, }, 250, AddScrollHandlers);
            return;
        }
    }
    AddScrollHandlers();
}

function AddScrollHandlers() {
    $(window).scroll(_ => {
        let firstLine = SauceryFirstLoadedLine();
        if (!firstLine.length)
            return;
        let lastLine = SauceryLastLoadedLine();

        let firstLineNumber = LineNumber(firstLine);
        let lastLineNumber = LineNumber(lastLine);

        let firstLineTop = firstLine.offset().top;
        let lastLineTop = lastLine.offset().top;

        let windowTop = $(window).scrollTop();
        let windowBottom = windowTop + window.innerHeight;

        if (windowTop < firstLineTop + 40 && firstLineNumber > 1)
            LoadRange(firstLineNumber - 100, firstLineNumber - 1)
        else if (windowBottom > lastLineTop - 40 && lastLineNumber < SauceryLastLineNumber())
            LoadRange(lastLineNumber + 1, lastLineNumber + 100)
    });
    // TODO: hook keypress to detect 'start' or 'end' pressed
}

function LoadRange(start, end) {
    start = Math.min(Math.max(SauceryFirstLineNumber(), start), SauceryLastLineNumber());
    end = Math.max(start, end);

    // Subtract 1 to adjust 1-based startline to 0-based array index
    let startindex = start - 1;

    // Subtract 1 to adjust 1-based endline to 0-based array index
    // Add 1 to include line content up to next newline
    // Add 1 because slice() does not include the final value
    let endindex = end + 1;

    let offsets = SauceryLineOffsets.slice(startindex, endindex);
    let range = 'bytes=' + offsets[0] + '-' + offsets.slice(-1)[0];

    return $.ajax(window.location.pathname, {
        data: { format: 'raw', },
        headers: { Range: range, },
        success: (data => { InsertLines(start, offsets, data); }),
    });
}

function InsertLines(startline, offsets, data) {
    let tbody = $('.TextFile>table>tbody');
    if (tbody.length == 0)
        return;

    let base = offsets[0];
    let start = base;
    let linenumber = startline;
    let rows = offsets.slice(1).map(end => {
        let lineid = 'LINE' + linenumber;
        let tr = $('<tr>').attr('id', lineid);
        let content = data.slice(start - base, end - base);
        $('<a>').addClass('linenumber').text(linenumber).attr('href', '#'+lineid)
            .appendTo($('<td>').appendTo(tr));
        $('<a>').addClass('linecontent').text(content)
            .appendTo($('<td>').appendTo(tr));
        start = end;
        linenumber = linenumber + 1
        return tr;
    });

    if (!SauceryFirstLoadedLine().length || startline < LineNumber(SauceryFirstLoadedLine())) {
        tbody.prepend(rows);
    } else {
        tbody.append(rows);
    }
}
